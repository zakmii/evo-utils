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
import datetime

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

    if "current_agent_name" not in st.session_state and "agents" in st.session_state:
        st.session_state.current_agent_name = list(st.session_state.agents.keys())[0]


def set_custom_pages(pages_dict):
    st.session_state.custom_pages = pages_dict


def serve_app():  # Remove authenticator parameter
    # Check for the new 'logged_in' state variable
    if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
        st.warning("Please log in to access the application.")
        return

    _apply_visual_styling()
    assert "agents" in st.session_state, "No agents have been set. Use set_app_agents() to set agents prior to serve_app()"
    loop = st.session_state.get("event_loop")

    loop.run_until_complete(_main())


def _apply_visual_styling():
    """Apply visual styling with customization options"""
    try:
        background_url = st.session_state.get(
            "background_image",
            "https://www.nayuki.io/res/animated-floating-graph-nodes/floating-graph-nodes.png"
        )

        theme_color = st.session_state.get("theme_color", "rgba(40, 40, 60, 0.85)")

        page_bg_img = f"""
        <style>
        [data-testid="stAppViewContainer"] > .main {{
            background-image: linear-gradient({theme_color}, {theme_color}),
                        url("{background_url}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}

        [data-testid="stSidebar"] {{
            background-color: rgba(25, 25, 45, 0.9);
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }}
        [data-testid="stSidebar"] h1 {{
            color: #E0E0E0;
            text-align: center;
        }}
        [data-testid="stSidebar"] .stButton>button {{
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            background-color: rgba(255, 255, 255, 0.1);
            color: #E0E0E0;
            transition: background-color 0.3s ease, color 0.3s ease;
        }}
        [data-testid="stSidebar"] .stButton>button:hover {{
            background-color: rgba(255, 255, 255, 0.2);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }}
        [data-testid="stSidebar"] .stButton[data-testid*="logout_button"]>button {{
            background-color: rgba(220, 53, 69, 0.7);
            border: 1px solid rgba(220, 53, 69, 0.9);
        }}
        [data-testid="stSidebar"] .stButton[data-testid*="logout_button"]>button:hover {{
            background-color: rgba(220, 53, 69, 0.9);
        }}

        [data-testid="stHeader"] {{
            background-color: rgba(0,0,0,0);
        }}

        [data-testid="stChatMessage"] {{
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            margin-bottom: 10px;
            padding: 15px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .hover-section {{
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            padding: 1.5rem;
            border-radius: 8px;
            background-color: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            margin-bottom: 1rem;
        }}
        .hover-section:hover {{
            transform: translateY(-5px) scale(1.01);
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3);
            background-color: rgba(255, 255, 255, 0.06);
        }}

        .nav-link {{
            padding: 10px 16px;
            text-decoration: none;
            border-radius: 6px;
            margin-bottom: 5px;
            display: block;
            width: 100%;
            color: #B0C4DE;
            text-align: left;
            background-color: transparent;
            border: none;
            font-size: 1.05em;
        }}
        .nav-link:hover {{
            background-color: rgba(255, 255, 255, 0.1);
            color: white;
        }}
        .nav-link.active {{
            background-color: rgba(70, 130, 180, 0.3);
            font-weight: bold;
            color: white;
        }}

        .stMarkdown {{
            color: #EAEAEA;
        }}
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
            color: #ADD8E6;
        }}
        .stMarkdown a {{
             color: #87CEEB;
             text-decoration: none;
        }}
         .stMarkdown a:hover {{
             text-decoration: underline;
         }}

        .stExpander {{
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background-color: rgba(255, 255, 255, 0.03);
        }}
        .stExpander header {{
             color: #B0C4DE;
        }}

        </style>
        """
        st.markdown(page_bg_img, unsafe_allow_html=True)
    except Exception as e:
        st.session_state.logger.warning(f"Could not set background: {str(e)}")


def _initialize_session_state(**kwargs):
    if "logger" not in st.session_state:
        st.session_state.logger = logging.getLogger(__name__)
        st.session_state.logger.handlers = []
        st.session_state.logger.setLevel(logging.INFO)
        st.session_state.logger.addHandler(logging.StreamHandler())

    st.session_state.setdefault("event_loop", asyncio.new_event_loop())
    st.session_state.setdefault("default_api_key", None)
    st.session_state.setdefault("ui_disabled", False)
    st.session_state.setdefault("lock_widgets", False)
    ttl_seconds = kwargs.get("share_chat_ttl_seconds", 60*60*24*30)
    st.session_state.setdefault("share_chat_ttl_seconds", ttl_seconds)

    st.session_state.setdefault("logo_path", kwargs.get("logo_path", None))
    st.session_state.setdefault("app_title", kwargs.get("app_title", "AI Assistant"))
    st.session_state.setdefault("background_image", kwargs.get("background_image",
                                "https://www.nayuki.io/res/animated-floating-graph-nodes/floating-graph-nodes.png"))
    st.session_state.setdefault("theme_color", kwargs.get("theme_color", "rgba(0,0,0,0.7)"))
    st.session_state.setdefault("show_logo", kwargs.get("show_logo", True))
    st.session_state.setdefault("sidebar_content", kwargs.get("sidebar_content", None))

    st.session_state.setdefault("show_function_calls", kwargs.get("show_function_calls", False))
    st.session_state.setdefault("show_function_calls_status", kwargs.get("show_function_calls_status", True))

    st.session_state.setdefault("current_page", "intro")

    default_pages = {
        "intro": ("Introduction", _show_intro_page, None),
        "chat": ("Chatbot", None, None),
        "tutorial": ("Tutorial", _show_tutorial_page, None),
        "about": ("About Us", _show_about_page, None),
    }

    custom_pages = kwargs.get("custom_pages", {})
    all_pages = {**default_pages, **custom_pages}
    st.session_state.setdefault("pages", all_pages)

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


def _render_message(message):
    current_agent = st.session_state.agents[st.session_state.current_agent_name]
    current_agent_avatar = current_agent.avatar
    current_user_avatar = current_agent.user_avatar

    current_action = "*Thinking...*"

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

    # Query limit check
    if "query_limits" in st.session_state and \
       "last_query_reset" in st.session_state and \
       "user_token" in st.session_state and \
       "update_user_query_limits_func" in st.session_state:

        now = datetime.datetime.utcnow()
        try:
            last_reset_dt = datetime.datetime.fromisoformat(st.session_state["last_query_reset"])
        except ValueError:
            # Handle cases where last_query_reset might not be a valid ISO format string initially
            # For instance, if it was not set correctly or is None. Default to an old date to trigger reset.
            last_reset_dt = now - datetime.timedelta(hours=2) # Force reset if format is wrong
            st.session_state["last_query_reset"] = (now - datetime.timedelta(hours=2)).isoformat() # Correct it in session state


        if now - last_reset_dt > datetime.timedelta(hours=1):
            st.session_state["query_limits"] = 10
            st.session_state["last_query_reset"] = now.isoformat()

            update_func = st.session_state.update_user_query_limits_func
            token = st.session_state.get("user_token")
            if token and update_func:
                update_success, _ = update_func(
                    token,
                    st.session_state["query_limits"],
                    st.session_state["last_query_reset"]
                )
                if not update_success:
                    st.warning("Failed to sync query limit reset with the server.")
            elif not token:
                st.warning("User token not found, cannot sync query limit reset.")
            elif not update_func:
                st.warning("Update function not found, cannot sync query limit reset.")


        if st.session_state["query_limits"] <= 0:
            st.error("🚫 You have reached your query limit. Please upgrade your account or wait for the hourly reset.")
            st.toast("⚠️ Query limit reached. Please wait for the hourly reset or upgrade.", icon="⏳")
            # Ensure UI is not locked if we return early
            st.session_state.lock_widgets = False
            #st.rerun() # Rerun to reflect the locked state and error message
            return

    agent = st.session_state.agents[st.session_state.current_agent_name]

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

            if message is not None and message.tool_calls is not None and st.session_state.show_function_calls_status:
                if(len(message.tool_calls) > 0):
                    all_tool_calls = [f"`{tool_call.function.name}`" for tool_call in message.tool_calls]
                    distinct_tool_calls = set(all_tool_calls)
                    status.update(label = f"Checking sources: {', '.join(distinct_tool_calls)}")

            messages.append(message)

            info = {"session_id": session_id, "message": message.model_dump(), "agent": st.session_state.current_agent_name}
            st.session_state.logger.info(info)

    agent.display_messages.append(messages[-1])
    agent.render_delayed_messages()

    # Decrement query limit after successful processing
    if "query_limits" in st.session_state and \
       "user_token" in st.session_state and \
       "update_user_query_limits_func" in st.session_state:
        st.session_state["query_limits"] -= 1

        update_func = st.session_state.update_user_query_limits_func
        token = st.session_state.get("user_token")
        if token and update_func:
            update_success, _ = update_func(
                token,
                st.session_state["query_limits"],
                st.session_state["last_query_reset"] # This is the existing reset time, not now
            )
            if not update_success:
                st.warning("Failed to sync query limit update with the server.")
        elif not token:
            st.warning("User token not found, cannot sync query limit update.")
        elif not update_func:
            st.warning("Update function not found, cannot sync query limit update.")
    elif "query_limits" in st.session_state : # if other conditions for update not met, still decrement locally
        st.session_state["query_limits"] -=1


    def render_messages():
        with st.expander("Full context"):
            all_json = [message.model_dump() for message in messages]
            st.write(all_json)

    render_context = UIOnlyMessage(render_messages, role=ChatRole.SYSTEM, icon="🛠️", type="tool_use")
    agent.display_messages.append(render_context)

    st.session_state.lock_widgets = False
    st.rerun()


async def _handle_chat_input(given_prompt = None):
    if prompt := st.chat_input(disabled=False, on_submit=_lock_ui):
        await _process_input(prompt)
        return


def _lock_ui():
    st.session_state.lock_widgets = True


def _clear_chat_current_agent():
    current_agent = st.session_state.agents[st.session_state.current_agent_name]
    current_agent.display_messages = []
    current_agent.delayed_display_messages = []
    current_agent.tokens_used_prompt = 0
    current_agent.tokens_used_completion = 0
    current_agent.chat_history = []


def _render_sidebar():  # Remove authenticator parameter
    """Render the sidebar with dynamic pages."""
    if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
        return

    current_agent = None
    if "agents" in st.session_state and "current_agent_name" in st.session_state:
        if st.session_state.current_agent_name in st.session_state.agents:
            current_agent = st.session_state.agents[st.session_state.current_agent_name]

    with st.sidebar:
        if st.session_state.get("show_logo", True):
            logo_path = st.session_state.get("logo_path")
            app_title = st.session_state.get("app_title", "AI Assistant")

            if logo_path:
                logo_base64 = get_img_as_base64(logo_path)
                if logo_base64:
                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                            <img src="data:image/png;base64,{logo_base64}" alt="Logo" style="height: 150px;">
                            <h1 style="margin: 0; font-size: 44px;">{app_title}</h1>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                            <h1 style="margin: 0; font-size: 44px;">{app_title}</h1>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                    <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                        <h1 style="margin: 0; font-size: 44px;">{app_title}</h1>
                    </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"👤 Welcome **{st.session_state.get('username', 'N/A')}**")
        st.markdown("---")

        if st.session_state.get("sidebar_content"):
            sidebar_content = st.session_state.get("sidebar_content")
            st.markdown(sidebar_content, unsafe_allow_html=True)
            st.markdown("---")

        for page_id, page_info in st.session_state.pages.items():
            if isinstance(page_info, tuple):
                if len(page_info) >= 3:
                    page_name, _, icon = page_info
                elif len(page_info) == 2:
                    page_name, _, icon = page_info[0], page_info[1], None
                else:
                    page_name, _, icon = page_info[0], None, None

            else:
                page_name, _, icon = str(page_info), None, None

            button_label = page_name
            if icon:
                button_label = f"{icon} {page_name}"

            if st.button(
                button_label,
                key=f"nav_{page_id}",
                help=f"Go to {page_name} page",
                use_container_width=True
            ):
                st.session_state.current_page = page_id
                st.rerun()

        st.markdown("---")

        if st.session_state.current_page == "chat" and current_agent is not None and "agents" in st.session_state:
            agent_names = list(st.session_state.agents.keys())

            st.markdown("### Assistant Settings")
            current_agent_name = st.selectbox(
                label="**Select Assistant**",
                options=agent_names,
                key="current_agent_name",
                disabled=st.session_state.lock_widgets,
                label_visibility="visible"
            )

            if hasattr(current_agent, "render_sidebar"):
               current_agent.render_sidebar()

            st.markdown("---")
            st.markdown("### Chat Controls")

            col1, col2 = st.columns(2)

            with col1:
                st.button(
                    label="🗑️ Clear Chat",
                    on_click=_clear_chat_current_agent,
                    disabled=st.session_state.lock_widgets,
                    use_container_width=True
                )

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
                        label="🔗 Share Chat",
                        on_click=_share_chat,
                        disabled=st.session_state.lock_widgets,
                        use_container_width=True
                    )

            if st.session_state.get("show_function_calls_option", True):
                st.checkbox(
                    "🛠️ Show full context",
                    key="show_function_calls",
                    disabled=st.session_state.lock_widgets,
                    help="Display the detailed function calls and responses made by the assistant."
                )


def _share_chat():
    try:
        current_agent = st.session_state.agents[st.session_state.current_agent_name]

        session_state_bytes_rep = dill.dumps(st.session_state)
        session_state_str_rep = base64.b64encode(session_state_bytes_rep).decode('utf-8')

        chat_data_dict = {"display_messages": current_agent.display_messages,
                   "agent_greeting": current_agent.greeting,
                   "agent_system_prompt": current_agent.system_prompt,
                   "agent_avatar": current_agent.avatar,
                   "session_state": session_state_str_rep,
                   }

        chat_data_bytes_rep = dill.dumps(chat_data_dict)
        chat_data_str_rep = base64.b64encode(chat_data_bytes_rep).decode('utf-8')

        async def summarize():
            agent_based_summary_prompt = "I am preparing to share this chat with others. Please summarize it in a few sentences."
            agent_based_summary = await current_agent.chat_round_str(agent_based_summary_prompt)
            return agent_based_summary

        agent_based_summary = asyncio.run(summarize())

        redis = Redis.from_env()

        key = st.session_state.page_title + "@" + current_agent.name + "@" + hashlib.md5(chat_data_str_rep.encode()).hexdigest()
        keycheck = redis.get(key)

        access_count = 0
        if keycheck is not None:
            access_count = keycheck["access_count"] + 1

        agent_model = current_agent.engine.model if current_agent.engine.model else "Unknown"
        convo_cost = current_agent.get_convo_cost()
        current_date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        save_dict = {"summary": agent_based_summary,
                     "agent_name": current_agent.name,
                     "agent_chat_cost": convo_cost,
                     "agent_model": agent_model,
                     "agent_description": current_agent.description,
                     "access_count": access_count,
                     "chat_data": chat_data_str_rep,
                     "chat_date": current_date_str,
                     }

        new_ttl_seconds = st.session_state.share_chat_ttl_seconds
        redis.set(key, save_dict, ex=new_ttl_seconds)

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
        redis = Redis.from_env()
        session_dict_raw = redis.get(session_id)

        # Ensure session_dict_raw is treated as bytes if it's not None, then decode
        if session_dict_raw is not None:
            if isinstance(session_dict_raw, bytes):
                session_dict_raw = session_dict_raw.decode('utf-8')
            session_dict = json.loads(session_dict_raw) # Parse JSON string to dict
        else:
            session_dict = None # Explicitly set to None if key not found

        if session_dict is None:
            raise ValueError(f"Session Key {session_id} not found in database")

        chat_data_str_rep = session_dict["chat_data"]
        chat_data_bytes_rep = base64.b64decode(chat_data_str_rep.encode('utf-8'))
        chat_data = dill.loads(chat_data_bytes_rep)

        new_ttl_seconds = st.session_state.share_chat_ttl_seconds
        access_count = session_dict["access_count"] + 1
        session_dict["access_count"] = access_count

        redis.set(session_id, session_dict, ex=new_ttl_seconds)

        display_messages = chat_data["display_messages"]
        agent_system_prompt = chat_data["agent_system_prompt"]
        agent_greeting = chat_data["agent_greeting"]
        agent_avatar = chat_data["agent_avatar"]

        st_session_state_str_rep = chat_data["session_state"]
        st_session_state_bytes_rep = base64.b64decode(st_session_state_str_rep.encode('utf-8'))
        st.session_state = dill.loads(st_session_state_bytes_rep)

        agent_name = session_dict["agent_name"]
        agent_description = session_dict["agent_description"]
        agent_chat_cost = session_dict["agent_chat_cost"]
        agent_model = session_dict["agent_model"]
        agent_summary = session_dict["summary"]
        chat_date = session_dict.get("chat_date", "N/A") # Correctly get chat_date

        if "first_func_calls_off_flag" not in st.session_state:
            st.session_state.show_function_calls = False
            st.session_state.first_func_calls_off_flag = True

        ttl_human = _seconds_to_days_hours(redis.ttl(session_id))

        with st.expander("Details"):
            st.markdown(f"##### This chat record will expire in {ttl_human}. Revisiting this URL will reset the expiration timer.")
            st.markdown(f"You can chat with this agent [here](/), selecting *{agent_name}* in the sidebar.")
            st.checkbox("🛠️ Show full message contexts",
                        key="show_function_calls",
                        value = False)
            st.markdown("**Chat date:** " + str(chat_date))
            st.markdown("**Chat summary:** " + str(agent_summary))
            st.markdown("**Chat access count:** " + str(access_count))
            st.markdown(f"**Chat Cost:** ${0.01 + agent_chat_cost:.2f} (includes summary generation)")
            st.markdown("**Agent Description:** " + str(agent_description))
            st.markdown("**Agent Model:** " + str(agent_model))
            st.markdown("**Agent System Prompt (*at time of chat share*):**")
            st.code(str(agent_system_prompt), language=None, wrap_lines=True, line_numbers=True)

        st.header(agent_name)

        with st.chat_message("assistant", avatar = agent_avatar):
            st.write(agent_greeting)

        for message in display_messages:
            _render_message(message)

    except Exception as e:
        st.session_state.logger.error(f"Error connecting to Redis: {e}")
        st.write(f"Error connecting to database.")


def _show_intro_page():
    st.markdown(
        """
        <div style="display: flex; align-items: center;">
            <h1 style="margin-right: 10px;">Welcome to the AI Assistant</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

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

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("Start Chatting →", use_container_width=True):
            st.session_state.current_page = "chat"
            st.rerun()


def _show_tutorial_page():
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


async def _main():  # Remove authenticator parameter
    # Check for the new 'logged_in' state variable
    if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
        st.error("Access denied. Please log in.")
        return

    if "session_id" in st.query_params:
        _render_shared_chat()
        return

    else:
        _render_sidebar()  # Remove authenticator argument

        current_page = st.session_state.current_page

        if current_page in st.session_state.pages and st.session_state.pages[current_page][1] is not None:
            page_render_func = st.session_state.pages[current_page][1]
            page_render_func()

        elif current_page == "chat":
            if "agents" in st.session_state and "current_agent_name" in st.session_state:
                if st.session_state.current_agent_name in st.session_state.agents:
                    current_agent = st.session_state.agents[st.session_state.current_agent_name]

                    header_style = st.session_state.get("header_style", "margin-bottom: 20px; text-align: center; color: #C0C0C0;")
                    st.markdown(f"""
                        <h1 style="{header_style}">{current_agent.name}</h1>
                    """, unsafe_allow_html=True)

                    # Display the greeting message directly using st.markdown
                    with st.chat_message("assistant", avatar=current_agent.avatar):
                        # Render the greeting text directly. Streamlit's chat_message handles the container.
                        st.markdown(current_agent.greeting, unsafe_allow_html=True)  # Keep unsafe_allow_html if greeting contains markdown/HTML

                    for message in current_agent.display_messages:
                        _render_message(message)

                    await _handle_chat_input()
                else:
                    st.warning("The selected agent is not available. Please choose another agent.")
            else:
                st.info("No agents have been configured. Please configure agents to use the chat functionality.")
        else:
            st.error(f"Page '{current_page}' not found or has no render function.")



