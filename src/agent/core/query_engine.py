"""
Agent主循环引擎

循环执行：上下文压缩 → Query AI → Tool Use判断 → 工具路由 → Stop Hook
"""

import json
from typing import Dict, Any, List, Tuple, Optional

from src.utils import get_logger

logger = get_logger('query_engine')


class QueryEngine:
    """Agent主循环引擎

    负责执行核心的Agent处理循环：
    1. 构建系统Prompt
    2. 上下文压缩
    3. Query AI（支持工具调用）
    4. Tool Use判断与路由
    5. Stop Hook判断
    6. 循环直至完成
    """

    def __init__(self, ai_client, tool_router, context_manager, prompt_builder,
                 max_rounds: int = 20, tool_call_limit: int = 50):
        self.ai_client = ai_client
        self.tool_router = tool_router
        self.context_manager = context_manager
        self.prompt_builder = prompt_builder
        self.max_rounds = max_rounds
        self.tool_call_limit = tool_call_limit

    def run(self, session_state: Dict, user_input: str,
            conversation_history: List[Dict] = None,
            session_context: Dict = None) -> Dict:
        """执行一轮完整的Agent处理循环

        Args:
            session_state: 会话状态字典
            user_input: 用户输入
            conversation_history: 对话历史
            session_context: 构建prompt需要的会话上下文

        Returns:
            dict: 包含 final_response, metadata 的结果
        """
        conversation_history = conversation_history or []
        session_context = session_context or {}

        # 构建消息
        messages = self._build_messages(session_context, conversation_history, user_input)

        # 上下文压缩
        tools = self.tool_router.get_all_tools() if self.tool_router else []
        messages = self.context_manager.check_and_compress(messages, tools)

        # 多轮交互
        round_count = 0
        tool_call_count = 0
        final_response = ""
        interactions = []

        while round_count < self.max_rounds and tool_call_count < self.tool_call_limit:
            round_count += 1
            logger.debug(f"第{round_count}轮交互开始")

            try:
                response = self.ai_client.chat_with_tools(messages, tools, "auto")
            except Exception as e:
                logger.error(f"AI调用失败: {str(e)}")
                final_response = f"AI调用失败: {str(e)}"
                break

            if response.has_tool_calls():
                messages.append(response.to_message())
                for tool_call in response.tool_calls:
                    tool_call_count += 1
                    result, interaction = self._process_tool_call(tool_call)
                    interactions.append(interaction)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get('id', ''),
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            else:
                final_response = response.content or ""
                interactions.append({"response": final_response})
                break

        # 更新上下文状态到session_state
        session_state['context_usage'] = self.context_manager.state.usage_ratio
        session_state['tool_calls'] = session_state.get('tool_calls', 0) + tool_call_count

        metadata = {
            "round_count": round_count,
            "tool_call_count": tool_call_count,
            "context_usage": self.context_manager.state.usage_ratio,
            "interactions": interactions
        }

        logger.debug(f"对话完成: {round_count}轮, {tool_call_count}次工具调用")
        return {
            "final_response": final_response,
            "metadata": metadata,
            "messages": messages
        }

    def run_stream(self, session_state: Dict, user_input: str,
                   conversation_history: List[Dict] = None,
                   session_context: Dict = None):
        """流式执行（无工具调用）

        Args:
            session_state: 会话状态字典
            user_input: 用户输入
            conversation_history: 对话历史
            session_context: 构建prompt需要的会话上下文

        Yields:
            str: AI响应的文本片段
        """
        conversation_history = conversation_history or []
        session_context = session_context or {}

        messages = self._build_messages(session_context, conversation_history, user_input)
        tools = self.tool_router.get_all_tools() if self.tool_router else []
        messages = self.context_manager.check_and_compress(messages, tools)

        full_response = ""

        try:
            for chunk in self.ai_client.chat(messages):
                full_response += chunk
                yield chunk
        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}")
            yield f"[错误: {str(e)}]"
            return

        # 返回完整响应供外部保存
        return full_response

    def _build_messages(self, session_context: Dict,
                        conversation_history: List[Dict],
                        user_input: str) -> List[Dict]:
        """构建对话消息列表"""
        messages = []

        # 系统提示
        if self.prompt_builder:
            system_prompt = self.prompt_builder.build(session_context)
            messages.append({"role": "system", "content": system_prompt})

        # 对话历史
        messages.extend(conversation_history)

        # 用户输入
        if user_input:
            messages.append({"role": "user", "content": user_input})

        return messages

    def _process_tool_call(self, tool_call: Dict) -> Tuple[Dict, Dict]:
        """处理单个工具调用

        Returns:
            tuple: (工具执行结果, 交互记录)
        """
        tool_name = tool_call.get('function', {}).get('name', '')
        args_str = tool_call.get('function', {}).get('arguments', '{}')

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}

        logger.debug(f"执行工具: {tool_name}")

        if self.tool_router:
            result = self.tool_router.execute(tool_name, args)
        else:
            result = {"error": "ToolRouter未初始化"}

        interaction = {
            "tool": tool_name,
            "args": args,
            "result": result
        }
        return result, interaction
