from kani import Kani
from kani import AIParam, ai_function
from typing import Annotated, Optional, List
from kani.engines.base import BaseCompletion, Completion

class TokenCounterKani(Kani):
    """A Kani that keeps track of tokens used over the course of the conversation."""
    def __init__(self, 
                 *args, 
                 prompt_tokens_cost = None, 
                 completion_tokens_cost = None,                  
                 **kwargs):

        super().__init__(*args, **kwargs)

        self.prompt_tokens_cost = prompt_tokens_cost
        self.completion_tokens_cost = completion_tokens_cost
        self.tokens_used_prompt = 0
        self.tokens_used_completion = 0

        self.description = f"TokenCounterKani(prompt_tokens_cost={prompt_tokens_cost}, completion_tokens_cost={completion_tokens_cost})"
        self.avatar = "🧮"
        self.user_avatar = "👤"
        self.greeting = "Hello, I'm a token counter assistant. I will keep track of the number of tokens used in the prompt and completion."

    def get_convo_cost(self):
        """Get the total cost of the conversation so far."""
        if self.prompt_tokens_cost is None or self.completion_tokens_cost is None:
            return None
        
        return (self.tokens_used_prompt / 1000.0) * self.prompt_tokens_cost + (self.tokens_used_completion / 1000.0) * self.completion_tokens_cost

    async def get_model_completion(self, include_functions: bool = True, **kwargs) -> BaseCompletion:
        """Overrides the default get_model_completion to track tokens used.
        See https://github.com/zhudotexe/kanpai/blob/cc603705d353e4e9b9aa3cf9fbb12e3a46652c55/kanpai/base_kani.py#L48
        """
        completion = await super().get_model_completion(include_functions, **kwargs)
        self.tokens_used_prompt += completion.prompt_tokens
        self.tokens_used_completion += completion.completion_tokens

        message = completion.message
        # HACK: sometimes openai's function calls are borked; we fix them here
        if (function_call := message.function_call) and function_call.name.startswith("functions."):
            fixed_name = function_call.name.removeprefix("functions.")
            message = message.copy_with(function_call=function_call.copy_with(name=fixed_name))
            return Completion(
                message, prompt_tokens=completion.prompt_tokens, completion_tokens=completion.completion_tokens
            )
        return completion
    

    async def estimate_next_tokens_cost(self):
        """Estimate the cost of the next message (not including the response)."""
        # includes all previous messages, plus the current
        return sum(self.message_token_len(m) for m in await self.get_prompt()) + self.engine.token_reserve + self.engine.function_token_reserve(list(self.functions.values()))

