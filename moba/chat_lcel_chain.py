import gradio as gr
import json
import time
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Generator
import requests
import logging
import threading

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OllamaClient:
    """优化的Ollama客户端类"""

    def __init__(self, host: str = "http://192.168.100.17:11434"):
        self.host = host.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 60  # 增加超时时间

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False

    def get_models(self) -> List[str]:
        """获取可用模型列表"""
        try:
            response = self.session.get(f"{self.host}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            model_names = [model["name"] for model in models]
            logger.info(f"获取到模型列表: {model_names}")
            return model_names if model_names else ["qwen2.5:7b", "llama3.2:3b"]
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return ["qwen2.5:7b", "llama3.2:3b"]  # 默认模型

    def chat_stream(self, model: str, messages: List[Dict], **kwargs) -> Generator[str, None, None]:
        """流式聊天"""
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("num_predict", -1),
                }
            }

            logger.info(f"发送流式请求到模型 {model}")
            logger.debug(f"请求载荷: {json.dumps(payload, indent=2, ensure_ascii=False)}")

            response = self.session.post(
                f"{self.host}/api/chat",
                json=payload,
                stream=True,
                timeout=180
            )
            response.raise_for_status()

            result = ""
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        if chunk.get("message", {}).get("content"):
                            content = chunk["message"]["content"]
                            result += content
                            yield result
                        elif chunk.get("done"):
                            break
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON解析错误: {e}, 行内容: {line}")
                        continue

            if not result:
                yield "抱歉，模型没有返回任何内容。请检查模型是否正常运行。"

        except requests.exceptions.Timeout:
            error_msg = "请求超时，请检查网络连接或稍后重试"
            logger.error(error_msg)
            yield error_msg
        except requests.exceptions.ConnectionError:
            error_msg = f"无法连接到Ollama服务 ({self.host})，请确保服务正在运行"
            logger.error(error_msg)
            yield error_msg
        except Exception as e:
            error_msg = f"聊天请求失败: {str(e)}"
            logger.error(error_msg)
            yield error_msg

    def chat(self, model: str, messages: List[Dict], **kwargs) -> str:
        """非流式聊天"""
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("num_predict", -1),
                }
            }

            logger.info(f"发送非流式请求到模型 {model}")
            logger.debug(f"请求载荷: {json.dumps(payload, indent=2, ensure_ascii=False)}")

            response = self.session.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=180
            )
            response.raise_for_status()

            result = response.json()["message"]["content"]
            return result if result else "抱歉，模型没有返回任何内容。"

        except requests.exceptions.Timeout:
            return "请求超时，请检查网络连接或稍后重试"
        except requests.exceptions.ConnectionError:
            return f"无法连接到Ollama服务 ({self.host})，请确保服务正在运行"
        except Exception as e:
            error_msg = f"聊天请求失败: {str(e)}"
            logger.error(error_msg)
            return error_msg


class TimerDisplay:
    """计时器显示类"""

    def __init__(self):
        self.start_time = None
        self.is_running = False

    def start(self):
        """开始计时"""
        self.start_time = time.time()
        self.is_running = True

    def stop(self):
        """停止计时"""
        self.is_running = False

    def get_elapsed_time(self) -> str:
        """获取已用时间"""
        if not self.is_running or self.start_time is None:
            return "00:00"

        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes:02d}:{seconds:02d}"


class ChatManager:
    """聊天管理器"""

    def __init__(self):
        self.client = OllamaClient()
        self.conversation_history = []
        self.timer = TimerDisplay()
        self.system_prompts = {
            "默认": "",
            "编程助手": "你是一个专业的编程助手，擅长多种编程语言，能够提供清晰的代码示例和解释。请用中文回答。",
            "写作助手": "你是一个专业的写作助手，擅长创作、修改和优化各种文本内容。请用中文回答。",
            "学习导师": "你是一个耐心的学习导师，善于用简单易懂的方式解释复杂概念。请用中文回答。",
            "翻译专家": "你是一个专业的翻译专家，能够准确翻译多种语言，并保持原文的语调和风格。请用中文回答。"
        }

    def format_messages(self, history: List, current_message: str, system_prompt: str = "") -> List[Dict]:
        """格式化消息历史"""
        messages = []

        # 添加系统提示
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})

        # 处理历史消息
        if history:
            for entry in history:
                if isinstance(entry, dict) and "role" in entry and "content" in entry:
                    # 新格式：{"role": "user/assistant", "content": "..."}
                    messages.append(entry)
                elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    # 旧格式：[user_msg, assistant_msg]
                    user_msg, assistant_msg = entry[0], entry[1]
                    if user_msg and user_msg.strip():
                        messages.append({"role": "user", "content": user_msg})
                    if assistant_msg and assistant_msg.strip():
                        messages.append({"role": "assistant", "content": assistant_msg})

        # 添加当前消息
        if current_message.strip():
            messages.append({"role": "user", "content": current_message})

        logger.info(f"格式化后的消息数量: {len(messages)}")
        return messages

    def chat_response_stream(self, message: str, history: List, model: str,
                             system_prompt: str, temperature: float,
                             max_tokens: int) -> Generator[Tuple[List, str], None, None]:
        """流式聊天响应"""
        if not message.strip():
            yield history, "⏱️ 00:00"
            return

        # 开始计时
        self.timer.start()

        # 添加用户消息到历史
        new_history = history + [{"role": "user", "content": message}]

        # 添加空的助手回复
        new_history.append({"role": "assistant", "content": ""})

        try:
            messages = self.format_messages(history, message, system_prompt)

            chat_params = {
                "temperature": temperature,
                "num_predict": max_tokens if max_tokens > 0 else -1
            }

            # 开始流式响应
            for partial_response in self.client.chat_stream(model, messages, **chat_params):
                new_history[-1]["content"] = partial_response
                elapsed_time = self.timer.get_elapsed_time()
                yield new_history, f"⏱️ {elapsed_time}"

        except Exception as e:
            error_msg = f"生成回复时出错: {str(e)}"
            logger.error(error_msg)
            new_history[-1]["content"] = error_msg
            yield new_history, f"⏱️ {self.timer.get_elapsed_time()}"
        finally:
            self.timer.stop()
            final_time = self.timer.get_elapsed_time()
            yield new_history, f"✅ 完成 ({final_time})"

    def chat_response_non_stream(self, message: str, history: List, model: str,
                                 system_prompt: str, temperature: float,
                                 max_tokens: int) -> Tuple[List, str]:
        """非流式聊天响应"""
        if not message.strip():
            return history, "⏱️ 00:00"

        # 开始计时
        self.timer.start()

        try:
            messages = self.format_messages(history, message, system_prompt)

            chat_params = {
                "temperature": temperature,
                "num_predict": max_tokens if max_tokens > 0 else -1
            }

            response = self.client.chat(model, messages, **chat_params)

            # 添加消息到历史
            new_history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response}
            ]

            return new_history, f"✅ 完成 ({self.timer.get_elapsed_time()})"

        except Exception as e:
            error_msg = f"生成回复时出错: {str(e)}"
            logger.error(error_msg)
            new_history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": error_msg}
            ]
            return new_history, f"❌ 错误 ({self.timer.get_elapsed_time()})"
        finally:
            self.timer.stop()

    def export_conversation(self, history: List) -> str:
        """导出对话历史"""
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "conversation": []
        }

        for entry in history:
            if isinstance(entry, dict):
                export_data["conversation"].append(entry)
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                export_data["conversation"].extend([
                    {"role": "user", "content": entry[0]},
                    {"role": "assistant", "content": entry[1]}
                ])

        return json.dumps(export_data, ensure_ascii=False, indent=2)


def create_chat_interface():
    """创建聊天界面"""
    chat_manager = ChatManager()

    # 测试连接并获取可用模型
    if chat_manager.client.test_connection():
        available_models = chat_manager.client.get_models()
        connection_status = "✅ Ollama连接正常"
    else:
        available_models = ["qwen2.5:7b", "llama3.2:3b"]
        connection_status = "❌ Ollama连接失败，请检查服务是否运行"

    with gr.Blocks(
            title="Enhanced Ollama Chat",
            theme=gr.themes.Soft(),
            css="""
        .chat-container { max-width: 1200px; margin: 0 auto; }
        .settings-panel { background: #f8f9fa; padding: 15px; border-radius: 10px; }
        .status-panel { background: #e8f5e8; padding: 10px; border-radius: 5px; margin: 10px 0; }
        .timer-display { font-family: monospace; font-weight: bold; color: #2196F3; }
        """
    ) as demo:

        gr.Markdown("# 🤖 Enhanced Ollama Chat Assistant")
        gr.Markdown("功能完备的本地AI聊天界面，支持多模型、流式输出、计时器等功能")

        # 连接状态显示
        status_display = gr.Markdown(connection_status, elem_classes=["status-panel"])

        with gr.Row():
            with gr.Column(scale=4):
                # 主聊天区域
                chatbot = gr.Chatbot(
                    height=600,
                    type="messages",
                    show_label=False,
                    show_copy_button=True,
                    show_share_button=False
                )

                # 计时器显示
                timer_display = gr.Markdown("⏱️ 00:00", elem_classes=["timer-display"])

                with gr.Row():
                    msg_input = gr.Textbox(
                        placeholder="输入您的问题...",
                        container=False,
                        scale=4,
                        autofocus=True
                    )
                    send_btn = gr.Button("发送", variant="primary", scale=1)

                # 快捷按钮
                with gr.Row():
                    clear_btn = gr.Button("清空对话", size="sm")
                    export_btn = gr.Button("导出对话", size="sm")
                    regen_btn = gr.Button("重新生成", size="sm")

            with gr.Column(scale=1, elem_classes=["settings-panel"]):
                gr.Markdown("### ⚙️ 设置")

                # 模型选择
                model_dropdown = gr.Dropdown(
                    choices=available_models,
                    value=available_models[0] if available_models else "qwen2.5:7b",
                    label="模型",
                    info="选择要使用的模型"
                )

                # 角色设定
                system_dropdown = gr.Dropdown(
                    choices=list(chat_manager.system_prompts.keys()),
                    value="默认",
                    label="角色设定",
                    info="选择AI的角色"
                )

                # 自定义系统提示
                custom_system = gr.Textbox(
                    label="自定义提示",
                    placeholder="可选：输入自定义系统提示",
                    lines=3
                )

                # 高级参数
                with gr.Accordion("高级参数", open=False):
                    temperature = gr.Slider(
                        minimum=0.1,
                        maximum=2.0,
                        value=0.7,
                        step=0.1,
                        label="Temperature",
                        info="控制回答的随机性"
                    )

                    max_tokens = gr.Slider(
                        minimum=0,
                        maximum=4000,
                        value=0,
                        step=100,
                        label="最大令牌数",
                        info="0表示无限制"
                    )

                    stream_output = gr.Checkbox(
                        value=True,
                        label="流式输出",
                        info="实时显示生成内容"
                    )

                # 预设问题
                gr.Markdown("### 💡 示例问题")
                example_questions = [
                    "介绍一下你自己",
                    "用Python写一个快速排序",
                    "解释什么是机器学习",
                    "写一首关于春天的诗",
                    "如何提高编程技能？"
                ]

                for question in example_questions:
                    gr.Button(question, size="sm").click(
                        lambda q=question: q,
                        outputs=msg_input
                    )

        def get_system_prompt(system_choice, custom_prompt):
            """获取系统提示"""
            if custom_prompt.strip():
                return custom_prompt
            return chat_manager.system_prompts.get(system_choice, "")

        def respond(message, history, model, system_choice, custom_prompt,
                    temp, max_tok, stream):
            """响应用户消息"""
            if not message.strip():
                return history, "", "⏱️ 00:00"

            system_prompt = get_system_prompt(system_choice, custom_prompt)

            if stream:
                # 流式响应
                for new_history, timer_text in chat_manager.chat_response_stream(
                        message, history, model, system_prompt, temp, max_tok
                ):
                    yield new_history, "", timer_text
            else:
                # 非流式响应
                new_history, timer_text = chat_manager.chat_response_non_stream(
                    message, history, model, system_prompt, temp, max_tok
                )
                yield new_history, "", timer_text

        def clear_conversation():
            """清空对话"""
            return [], "", "⏱️ 00:00"

        def export_conversation(history):
            """导出对话"""
            if not history:
                return None, "没有对话记录可导出"

            try:
                export_content = chat_manager.export_conversation(history)
                filename = f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(export_content)

                return filename, f"对话已导出到 {filename}"
            except Exception as e:
                return None, f"导出失败: {str(e)}"

        def regenerate_response(history, model, system_choice, custom_prompt,
                                temp, max_tok, stream):
            """重新生成最后一个回答"""
            if not history or len(history) < 2:
                return history, "⏱️ 00:00"

            # 移除最后一个助手回答
            if history[-1].get("role") == "assistant":
                last_user_message = None
                # 找到最后一个用户消息
                for i in range(len(history) - 2, -1, -1):
                    if history[i].get("role") == "user":
                        last_user_message = history[i]["content"]
                        break

                if last_user_message:
                    # 移除最后一个助手回答
                    new_history = history[:-1]
                    system_prompt = get_system_prompt(system_choice, custom_prompt)

                    if stream:
                        for updated_history, timer_text in chat_manager.chat_response_stream(
                                last_user_message, new_history[:-1], model, system_prompt, temp, max_tok
                        ):
                            yield updated_history, timer_text
                    else:
                        updated_history, timer_text = chat_manager.chat_response_non_stream(
                            last_user_message, new_history[:-1], model, system_prompt, temp, max_tok
                        )
                        yield updated_history, timer_text
                else:
                    yield history, "⏱️ 00:00"
            else:
                yield history, "⏱️ 00:00"

        # 事件绑定
        msg_input.submit(
            respond,
            inputs=[msg_input, chatbot, model_dropdown, system_dropdown,
                    custom_system, temperature, max_tokens, stream_output],
            outputs=[chatbot, msg_input, timer_display]
        )

        send_btn.click(
            respond,
            inputs=[msg_input, chatbot, model_dropdown, system_dropdown,
                    custom_system, temperature, max_tokens, stream_output],
            outputs=[chatbot, msg_input, timer_display]
        )

        clear_btn.click(
            clear_conversation,
            outputs=[chatbot, msg_input, timer_display]
        )

        export_btn.click(
            export_conversation,
            inputs=[chatbot],
            outputs=[gr.File(), gr.Textbox(visible=False)]
        )

        regen_btn.click(
            regenerate_response,
            inputs=[chatbot, model_dropdown, system_dropdown, custom_system,
                    temperature, max_tokens, stream_output],
            outputs=[chatbot, timer_display]
        )

    return demo


if __name__ == "__main__":
    import socket


    def find_free_port(start_port=7860, max_attempts=10):
        """找到可用的端口"""
        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                continue
        return None


    # 创建和启动应用
    demo = create_chat_interface()

    # 找到可用端口
    free_port = find_free_port()
    if free_port is None:
        print("无法找到可用端口，使用随机端口")
        free_port = 0  # 让系统分配随机端口

    print(f"正在启动应用，端口: {free_port}")

    # 启动配置
    try:
        demo.launch(
            server_name="127.0.0.1",
            server_port=free_port,
            share=False,
            debug=True,  # 开启调试模式便于排查问题
            show_error=True,
            inbrowser=True,
            quiet=False  # 显示详细日志
        )
    except Exception as e:
        print(f"启动失败，尝试使用备用配置: {e}")
        # 备用启动配置
        demo.launch(
            server_name="127.0.0.1",
            server_port=0,
            share=False,
            debug=True,
            show_error=True,
            inbrowser=False,
            quiet=False
        )