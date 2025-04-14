import streamlit as st
import logging
from kani import ChatRole, ChatMessage
import asyncio
from upstash_redis import Redis
import base64
import dill
import hashlib
import urllib.parse
from kani_utils.utils import _seconds_to_days_hours, _sync_generator_from_kani_streammanager
import json
import random

class UIOnlyMessage:
    def __init__(self, func, role=ChatRole.ASSISTANT, icon="💡", type = "ui_element"):
        self.func = func # the function that will render the UI element
        self.role = role
        self.icon = icon
        self.type = type # the type of message, e.g. "ui_element" or "tool_use"


def get_img_as_base64(file_path:str):
    """Load an image file and return it as a base64 encoded string."""
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except Exception as e:
        st.warning(f"Could not load image {file_path}: {str(e)}")
        return None


def initialize_app_config(**kwargs):
    """Initialize app configuration with support for custom pages."""
    _initialize_session_state(**kwargs)

    # this is kind of a hack, we want the user to be able to configure the default settings for
    # which needs to be set in the session state, so we pass in kwargs to _initialize_session_state() above, but they can't
    # go to set_page_config below, so we remove them here
    # Handle custom configuration parameters
    params_to_remove = [
        "show_function_calls", "share_chat_ttl_seconds", "show_function_calls_status",
        "logo_path", "app_title", "background_image", "theme_color", "custom_pages"
    ]

    for param in params_to_remove:
        if param in kwargs:
            if param == "logo_path":
                st.session_state.logo_path = kwargs.pop(param)
            elif param == "app_title":
                st.session_state.app_title = kwargs.pop(param)
            elif param == "background_image":
                st.session_state.background_image = kwargs.pop(param)
            elif param == "theme_color":
                st.session_state.theme_color = kwargs.pop(param)
            elif param == "custom_pages":
                # Save to session state AND remove from kwargs to avoid the error
                st.session_state.custom_pages = kwargs.pop("custom_pages", {})
            else:
                kwargs.pop(param)

    defaults = {
        "page_title": "Kani AI",
        "page_icon": None,
        "layout": "centered",
        "initial_sidebar_state": "collapsed",
        "menu_items": {
            "Get Help": "https://github.com/monarch-initiative/agent-smith-ai",
            "Report a Bug": "https://github.com/monarch-initiative/agent-smith-ai/issues",
            "About": "Agent Smith (AI) is a framework for developing tool-using AI-based chatbots.",
        }
    }

    # set the page title to the session_state as we'll need it later
    st.session_state.page_title = kwargs.get("page_title", defaults["page_title"])

    st.set_page_config(
        **{**defaults, **kwargs}
    )


def set_app_agents(agents_func, reinit = False):
    if "agents" not in st.session_state or reinit:
        agents = agents_func()
        st.session_state.agents = agents
        st.session_state.agents_func = agents_func

        if not reinit:
            st.session_state.current_agent_name = list(st.session_state.agents.keys())[0]

    # Ensure current_agent_name is set even if agents are already in session_state
    if "current_agent_name" not in st.session_state and "agents" in st.session_state:
        st.session_state.current_agent_name = list(st.session_state.agents.keys())[0]


def set_custom_pages(pages_dict):
    """
    Set custom pages for the application.

    Args:
        pages_dict: Dictionary mapping page_id to a tuple of (page_name, page_function, icon)
                   where page_function is a callable that renders the page content
    """
    st.session_state.custom_pages = pages_dict


def serve_app():
    _apply_visual_styling()
    assert "agents" in st.session_state, "No agents have been set. Use set_app_agents() to set agents prior to serve_app()"
    loop = st.session_state.get("event_loop")

    loop.run_until_complete(_main())


def _apply_visual_styling():
    """Apply visual styling with customization options"""
    try:
        # Get custom background or use default
        background_url = st.session_state.get(
            "background_image",
            "https://www.nayuki.io/res/animated-floating-graph-nodes/floating-graph-nodes.png"
        )

        # Get custom theme color or use default
        theme_color = st.session_state.get("theme_color", "rgba(0,0,0,0.7)")

        # Apply background with customizations
        page_bg_img = f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: linear-gradient({theme_color}, {theme_color}),
                        url("{background_url}");
            background-size: cover;
            background-position: center;
        }}

        [data-testid="stHeader"] {{
            background-color: rgba(0,0,0,0);
        }}

        /* Custom hover CSS for sections */
        .hover-section {{
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            padding: 1rem;
            border-radius: 4px;
        }}
        .hover-section:hover {{
            transform: translateY(-15px) scale(1.02);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.25);
        }}

        /* Custom navigation styling */
        .nav-link {{
            padding: 8px 16px;
            text-decoration: none;
            border-radius: 4px;
            margin-bottom: 4px;
            display: inline-block;
            width: 100%;
            color: #444;
        }}
        .nav-link:hover {{
            background-color: #f0f2f6;
        }}
        .nav-link.active {{
            background-color: #e6e9ef;
            font-weight: bold;
        }}
        </style>
        """
        st.markdown(page_bg_img, unsafe_allow_html=True)
    except Exception as e:
        st.session_state.logger.warning(f"Could not set background: {str(e)}")



# Initialize session states
def _initialize_session_state(**kwargs):
    if "logger" not in st.session_state:
        st.session_state.logger = logging.getLogger(__name__)
        st.session_state.logger.handlers = []
        st.session_state.logger.setLevel(logging.INFO)
        st.session_state.logger.addHandler(logging.StreamHandler())

    st.session_state.setdefault("event_loop", asyncio.new_event_loop())
    st.session_state.setdefault("default_api_key", None)  # Store the original API key
    st.session_state.setdefault("ui_disabled", False)
    st.session_state.setdefault("lock_widgets", False)
    ttl_seconds = kwargs.get("share_chat_ttl_seconds", 60*60*24*30)  # 30 days default
    st.session_state.setdefault("share_chat_ttl_seconds", ttl_seconds)

    # Default UI configurations
    st.session_state.setdefault("logo_path", kwargs.get("logo_path", None))
    st.session_state.setdefault("app_title", kwargs.get("app_title", "AI Assistant"))
    st.session_state.setdefault("background_image", kwargs.get("background_image",
                                "https://www.nayuki.io/res/animated-floating-graph-nodes/floating-graph-nodes.png"))
    st.session_state.setdefault("theme_color", kwargs.get("theme_color", "rgba(0,0,0,0.7)"))
    st.session_state.setdefault("show_logo", kwargs.get("show_logo", True))
    st.session_state.setdefault("sidebar_content", kwargs.get("sidebar_content", None))

    st.session_state.setdefault("show_function_calls", kwargs.get("show_function_calls", False))
    st.session_state.setdefault("show_function_calls_status", kwargs.get("show_function_calls_status", True))

    # Add navigation state
    st.session_state.setdefault("current_page", "intro")  # Changed default to 'intro'

    # Setup default pages
    default_pages = {
        "intro": ("Introduction", _show_intro_page, None),
        "chat": ("Chatbot", None, None),  # Chat is handled separately
        "tutorial": ("Tutorial", _show_tutorial_page, None),
        "about": ("About Us", _show_about_page, None),
    }

    # Merge default pages with custom pages
    custom_pages = kwargs.get("custom_pages", {})
    all_pages = {**default_pages, **custom_pages}
    st.session_state.setdefault("pages", all_pages)

    # Add navigation menu style
    st.session_state.setdefault(
        "nav_style",
        """
        <style>
        .nav-link {
            padding: 8px 16px;
            text-decoration: none;
            border-radius: 4px;
            margin-bottom: 4px;
            display: inline-block;
            width: 100%;
            color: #444;
        }
        .nav-link:hover {
            background-color: #f0f2f6;
        }
        .nav-link.active {
            background-color: #e6e9ef;
            font-weight: bold;
        }
        </style>
        """
    )


# Render chat message
def _render_message(message):
    current_agent = st.session_state.agents[st.session_state.current_agent_name]
    current_agent_avatar = current_agent.avatar
    current_user_avatar = current_agent.user_avatar

    current_action = "*Thinking...*"


    # first, check if this is a UIOnlyMessage,
    # if so, render it and return
    if isinstance(message, UIOnlyMessage):
        if message.role == ChatRole.USER:
            role = "user"
        else:
            role = "assistant"

        if message.type == "ui_element":
            with st.chat_message(role, avatar=message.icon):
                message.func()

        elif message.type == "tool_use" and st.session_state.show_function_calls:
            with st.chat_message(role, avatar=message.icon):
                message.func()

        return current_action

    elif message.role == ChatRole.USER:
        with st.chat_message("user", avatar = current_user_avatar):
            st.write(message.text)

    elif message.role == ChatRole.SYSTEM:
        with st.chat_message("assistant", avatar="ℹ️"):
            st.write(message.text)

    elif message.role == ChatRole.ASSISTANT and (message.tool_calls == None or message.tool_calls == []):
        with st.chat_message("assistant", avatar=current_agent_avatar):
            st.write(message.text)

    return current_action


async def _process_input(prompt):
    prompt = prompt.strip()

    # get current agent
    agent = st.session_state.agents[st.session_state.current_agent_name]

    # add user message to display and agent's history
    user_message = ChatMessage.user(prompt)
    _render_message(user_message)
    agent.display_messages.append(user_message)

    session_id = st.runtime.scriptrunner.add_script_run_ctx().streamlit_script_run_ctx.session_id
    info = {"session_id": session_id, "message": user_message.model_dump(), "agent": st.session_state.current_agent_name}
    st.session_state.logger.info(info)


    st.session_state.current_action = "*Thinking...*"

    messages = []
    message = None

    if st.session_state.show_function_calls_status:
        orig_status = "Thinking..."
        status = st.status(orig_status)

    with st.chat_message("assistant", avatar = agent.avatar):
        async for stream in agent.full_round_stream(prompt):
            if stream.role == ChatRole.ASSISTANT:
                st.write_stream(_sync_generator_from_kani_streammanager(stream))

            message = await stream.message()

            # compute the status as the most recent set of tool calls
            if message is not None and message.tool_calls is not None and st.session_state.show_function_calls_status:
                # I don't think message.tool_calls is ever None, but just in case
                if(len(message.tool_calls) > 0):
                    all_tool_calls = [f"`{tool_call.function.name}`" for tool_call in message.tool_calls]
                    distinct_tool_calls = set(all_tool_calls)
                    status.update(label = f"Checking sources: {', '.join(distinct_tool_calls)}")

            messages.append(message)

            # logging
            info = {"session_id": session_id, "message": message.model_dump(), "agent": st.session_state.current_agent_name}
            st.session_state.logger.info(info)


    # add the last message to the display
    agent.display_messages.append(messages[-1])
    # then any delayed UI-based messages
    agent.render_delayed_messages()

    # put together a UI element for the collected calls, and add it to the display list labeled as a tool use
    def render_messages():
        with st.expander("Full context"):
            all_json = [message.model_dump() for message in messages]
            st.write(all_json)

    render_context = UIOnlyMessage(render_messages, role=ChatRole.SYSTEM, icon="🛠️", type="tool_use")
    agent.display_messages.append(render_context)

    # unlock and rerun to clean rerender
    st.session_state.lock_widgets = False  # Step 5: Unlock the UI
    st.rerun()


# Handle chat input and responses
async def _handle_chat_input(given_prompt = None):
    if prompt := st.chat_input(disabled=False, on_submit=_lock_ui):
        await _process_input(prompt)
        return

    # not working...
    # if given_prompt:
    #     await _process_input(given_prompt)


# Lock the UI when user submits input
def _lock_ui():
    st.session_state.lock_widgets = True


def _clear_chat_current_agent():
    current_agent_name = st.session_state.current_agent_name
    agents_dict = st.session_state.agents_func()
    st.session_state.agents[current_agent_name] = agents_dict[current_agent_name]

    st.session_state.current_agent = agents_dict[current_agent_name]


def _render_sidebar():
    """Render the sidebar with dynamic pages based on session state."""
    # Only try to access current_agent if we're on the chat page and agents exist
    current_agent = None
    if "agents" in st.session_state and "current_agent_name" in st.session_state:
        if st.session_state.current_agent_name in st.session_state.agents:
            current_agent = st.session_state.agents[st.session_state.current_agent_name]

    with st.sidebar:
        # Customizable logo and title section
        if st.session_state.get("show_logo", True):
            logo_path = st.session_state.get("logo_path")
            app_title = st.session_state.get("app_title", "AI Assistant")

            if logo_path:
                # Logo image available
                logo_base64 = get_img_as_base64(logo_path)
                if logo_base64:
                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                            <img src="data:image/png;base64,{logo_base64}" alt="Logo" style="height: 150px;">
                            <h1 style="margin: 0; font-size: 44px;">{app_title}</h1>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    # Fallback if image can't be loaded
                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                            <h1 style="margin: 0; font-size: 44px;">{app_title}</h1>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                # No logo, just title
                st.markdown(f"""
                    <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                        <h1 style="margin: 0; font-size: 44px;">{app_title}</h1>
                    </div>
                """, unsafe_allow_html=True)

        # Custom sidebar content can be injected here
        if st.session_state.get("sidebar_content"):
            sidebar_content = st.session_state.get("sidebar_content")
            st.markdown(sidebar_content, unsafe_allow_html=True)

        st.markdown("---")

        # Navigation menu - dynamically render based on pages in session state
        # Custom CSS for navigation
        st.markdown(st.session_state.nav_style, unsafe_allow_html=True)

        # Navigation buttons with active state
        for page_id, page_info in st.session_state.pages.items():
            # Safely handle different tuple formats by unpacking with defaults
            if isinstance(page_info, tuple):
                if len(page_info) >= 3:
                    page_name, _, icon = page_info
                elif len(page_info) == 2:
                    page_name, _, icon = page_info[0], page_info[1], None
                else:
                    page_name, _, icon = page_info[0], None, None
            else:
                # Handle case where page_info is not a tuple
                page_name, _, icon = str(page_info), None, None

            button_label = page_name
            if icon:
                button_label = f"{icon} {page_name}"

            if st.button(
                button_label,
                key=f"nav_{page_id}",
                help=f"Go to {page_name} page",
                use_container_width=True,
            ):
                st.session_state.current_page = page_id
                st.rerun()

        st.markdown("---")

        # Only show agent controls on chat page if agents exist
        if st.session_state.current_page == "chat" and current_agent is not None and "agents" in st.session_state:
            # Agent selection with improved styling
            agent_names = list(st.session_state.agents.keys())

            st.markdown("### Choose Assistant")
            current_agent_name = st.selectbox(
                label="**Assistant**",
                options=agent_names,
                key="current_agent_name",
                disabled=st.session_state.lock_widgets,
                label_visibility="visible"
            )

            ## then the agent gets to render its sidebar info
            if hasattr(current_agent, "render_sidebar"):
               current_agent.render_sidebar()

            ## global UI elements with better styling
            col1, col2 = st.columns(2)

            with col1:
                st.button(
                    label="Clear Chat",
                    on_click=_clear_chat_current_agent,
                    disabled=st.session_state.lock_widgets,
                    use_container_width=True
                )

            # Try to get the database size from redis and log it
            dbsize = None
            try:
                redis = Redis.from_env()
                dbsize = redis.dbsize()
                st.session_state.logger.info(f"Shared chats DB size: {dbsize}")
            except Exception as e:
                st.session_state.logger.error(f"Error connecting to database, or no database to connect to: {str(e)}")

            if dbsize is not None:
                with col2:
                    st.button(
                        label="Share Chat",
                        on_click=_share_chat,
                        disabled=st.session_state.lock_widgets,
                        use_container_width=True
                    )

            # Optional UI elements based on configuration
            if st.session_state.get("show_function_calls_option", True):
                st.checkbox(
                    "🛠️ Show full context",
                    key="show_function_calls",
                    disabled=st.session_state.lock_widgets
                )


def _share_chat():
    try:
        current_agent = st.session_state.agents[st.session_state.current_agent_name]

        ## encode the chat data
        chat_data_dict = {"display_messages": current_agent.display_messages,
                   "agent_greeting": current_agent.greeting,
                   "agent_system_prompt": current_agent.system_prompt,
                   "agent_avatar": current_agent.avatar,
                   }

        chat_data_bytes_rep = dill.dumps(chat_data_dict)
        chat_data_str_rep = base64.b64encode(chat_data_bytes_rep).decode('utf-8')

        # generate chat summary
        async def summarize():
            agent_based_summary_prompt = "I am preparing to share this chat with others. Please summarize it in a few sentences."
            agent_based_summary = await current_agent.chat_round_str(agent_based_summary_prompt)
            return agent_based_summary

        agent_based_summary = asyncio.run(summarize())


        redis = Redis.from_env()

        # generate convo key, and compute access count (0 if new)
        key = st.session_state.page_title + "@" + current_agent.name + "@" + hashlib.md5(chat_data_str_rep.encode()).hexdigest()
        keycheck = redis.get(key)

        access_count = 0
        if keycheck is not None:
            access_count = keycheck["access_count"] + 1

        # computed metadata
        agent_model = current_agent.engine.model if current_agent.engine.model else "Unknown"
        convo_cost = current_agent.get_convo_cost()

        # chat_data stores the agents display_messages, greeting, system_prompt
        save_dict = {"summary": agent_based_summary,
                     "agent_name": current_agent.name,
                     "agent_chat_cost": convo_cost,
                     "agent_model": agent_model,
                     "agent_description": current_agent.description,
                     "access_count": access_count,
                     "chat_data": chat_data_str_rep,
                     }

        # save the chat with a new TTL
        new_ttl_seconds = st.session_state.share_chat_ttl_seconds
        redis.set(key, save_dict, ex=new_ttl_seconds)

        # display the share dialog
        url = urllib.parse.quote(key)
        ttl_human = _seconds_to_days_hours(new_ttl_seconds)

        @st.dialog("Share Chat")
        def share_dialog():
            st.write(f"Chat saved. Share this link: [Chat Link](/?session_id={url})\n\nThis link will expire in {ttl_human}. Any visit to the URL will reset the timer.")

        share_dialog()

    except Exception as e:
        st.write(f"Error saving chat.")


def _render_shared_chat():
    _apply_visual_styling()
    session_id = st.query_params["session_id"]

    try:
        # load the session data from the given key
        redis = Redis.from_env()
        session_dict_raw = redis.get(session_id)
        session_dict = json.loads(session_dict_raw)

        if session_dict is None:
            # throw an exception to trigger the error message
            raise ValueError(f"Session Key {session_id} not found in database")

        chat_data_str_rep = session_dict["chat_data"]
        chat_data_bytes_rep = base64.b64decode(chat_data_str_rep.encode('utf-8'))
        chat_data = dill.loads(chat_data_bytes_rep)

        # update ttl and access count, save back to redis
        new_ttl_seconds = st.session_state.share_chat_ttl_seconds
        access_count = session_dict["access_count"] + 1
        session_dict["access_count"] = access_count

        redis.set(session_id, session_dict, ex=new_ttl_seconds)


        # load chat data
        display_messages = chat_data["display_messages"]
        agent_system_prompt = chat_data["agent_system_prompt"]
        agent_greeting = chat_data["agent_greeting"]
        agent_avatar = chat_data["agent_avatar"]

        # load other metadata
        agent_name = session_dict["agent_name"]
        agent_description = session_dict["agent_description"]
        agent_chat_cost = session_dict["agent_chat_cost"]
        agent_model = session_dict["agent_model"]
        agent_summary = session_dict["summary"]

        # override show_function_calls to False, but only once
        if "first_func_calls_off_flag" not in st.session_state:
            st.session_state.show_function_calls = False
            st.session_state.first_func_calls_off_flag = True

        # compute the human-readable TTL
        ttl_human = _seconds_to_days_hours(redis.ttl(session_id))

        # display session details in expander
        with st.expander("Details"):
            st.markdown(f"##### This chat record will expire in {ttl_human}. Revisiting this URL will reset the expiration timer.")
            st.markdown(f"You can chat with this and other agents [here](/), selecting *{agent_name}* in the sidebar.")
            # render checkbox for showing function calls
            st.checkbox("🛠️ Show full message contexts",
                        key="show_function_calls",
                        value = False)
            st.markdown("**Chat summary:** " + str(agent_summary))
            st.markdown("**Chat access count:** " + str(access_count))
            st.markdown(f"**Chat Cost:** ${0.01 + agent_chat_cost:.2f} (includes summary generation)") # rounded up to 1c
            st.markdown("**Agent Description:** " + str(agent_description))
            st.markdown("**Agent Model:** " + str(agent_model))
            st.markdown("**Agent System Prompt:**")
            st.code(str(agent_system_prompt), language=None, wrap_lines=True, line_numbers=True)


        # display the chat as in the main UI: agent name, greeting, messages

        st.header(agent_name)

        with st.chat_message("assistant", avatar = agent_avatar):
            st.write(agent_greeting)

        for message in display_messages:
            _render_message(message)

    except Exception as e:
        st.session_state.logger.error(f"Error connecting to Redis: {e}")
        st.write(f"Error connecting to database.")


# Content display functions
def _show_intro_page():
    """Show the Introduction page with content"""
    st.markdown(
        """
        <div style="display: flex; align-items: center;">
            <!-- Main heading text -->
            <h1 style="margin-right: 10px;">Welcome to the AI Assistant</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- INTRO SECTIONS ---
    st.markdown(
        """
        <div class="hover-section">
          <h2>What is this assistant?</h2>
          <p>
            This is an AI-powered assistant designed to help you with various tasks.
            It can answer questions, provide information, and assist with your needs.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="hover-section">
            <h2>Key Features</h2>
            <ul>
              <li><strong>Intelligent Responses:</strong> Get smart, contextual answers to your questions</li>
              <li><strong>Tool Integration:</strong> The assistant can use various tools to help solve problems</li>
              <li><strong>Customizable:</strong> Adapt the assistant to your specific needs</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Centered button with custom styling
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("Start Chatting →", use_container_width=True):
            st.session_state.current_page = "chat"
            st.rerun()


def _show_tutorial_page():
    """Show the tutorial page."""
    st.title("Tutorials")
    st.markdown(
        """
        ## Getting Started
        Learn how to effectively use this Assistant with these tutorials:

        ### Basic Queries
        1. Ask simple questions
        2. Request specific information
        3. Explore complex topics

        ### Advanced Features
        1. Working with tools
        2. Multi-step conversations
        3. Problem-solving assistance
        """
    )


def _show_about_page():
    """Show the about page."""
    st.title("About Us")
    st.markdown(
        """
        ## About This Assistant

        This assistant is built using powerful AI technology to help users with various tasks.

        ### Technologies Used
        - OpenAI models
        - Streamlit framework
        - Kani conversation framework

        ### Contact

        For questions, feedback, or support:
        - Email: support@example.com
        - GitHub: [Project Repository](https://github.com/example/project)

        ### Developers
        - Development Team

        ### Report Issues
        If you encounter any problems, please report them on our GitHub repository.
        """
    )


# Main Streamlit UI
async def _main():
    if "session_id" in st.query_params:
        _render_shared_chat()
        return

    else:
        _render_sidebar()

        # Display content based on current page
        current_page = st.session_state.current_page

        # If the current page is in the pages dictionary and has a render function
        if current_page in st.session_state.pages and st.session_state.pages[current_page][1] is not None:
            # Call the render function for the current page
            page_render_func = st.session_state.pages[current_page][1]
            page_render_func()

        # Special case for chat page which has more complex rendering
        elif current_page == "chat":
            # Make sure agents are initialized before trying to render chat UI
            if "agents" in st.session_state and "current_agent_name" in st.session_state:
                if st.session_state.current_agent_name in st.session_state.agents:
                    # Original chat UI
                    current_agent = st.session_state.agents[st.session_state.current_agent_name]

                    # Enhanced header with styling and customizable formatting
                    header_style = st.session_state.get("header_style", "margin-bottom: 20px;")
                    st.markdown(f"""
                        <h1 style="{header_style}">{current_agent.name}</h1>
                    """, unsafe_allow_html=True)

                    # Custom chat container styling
                    greeting_container_class = st.session_state.get("greeting_container_class", "hover-section")

                    with st.chat_message("assistant", avatar=current_agent.avatar):
                        # Apply the styling with CSS instead of wrapping with div
                        st.markdown(f"""
                            <style>
                            .stMarkdown {{
                                /* Inherit styles from hover-section class */
                                transition: transform 0.3s ease, box-shadow 0.3s ease;
                                padding: 1rem;
                                border-radius: 4px;
                            }}
                            .stMarkdown:hover {{
                                transform: translateY(-15px) scale(1.02);
                                box-shadow: 0 12px 24px rgba(0, 0, 0, 0.25);
                            }}
                            </style>
                        """, unsafe_allow_html=True)
                        # Write the greeting directly without HTML wrapping
                        st.write(current_agent.greeting)

                    for message in current_agent.display_messages:
                        _render_message(message)

                    await _handle_chat_input()
                else:
                    # Handle case where current_agent_name exists but doesn't match any agent
                    st.warning("The selected agent is not available. Please choose another agent.")
            else:
                # Handle case where agents aren't initialized yet
                st.info("No agents have been configured. Please configure agents to use the chat functionality.")
        else:
            # If we get here, the page doesn't exist or has no render function
            st.error(f"Page '{current_page}' not found or has no render function.")



