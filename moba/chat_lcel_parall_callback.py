
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.runnables import RunnableParallel
import dotenv
from uuid import UUID
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig



class CustomCallbackHandler(BaseCallbackHandler):
    """自定义回调处理类"""

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], *, run_id: UUID,
                            parent_run_id: Optional[UUID] = None, tags: Optional[List[str]] = None,
                            metadata: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        print("======聊天模型结束执行======")

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, parent_run_id: Optional[UUID] = None,
                   **kwargs: Any) -> Any:
        print("======聊天模型结束执行======")

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], *, run_id: UUID,
                       parent_run_id: Optional[UUID] = None, tags: Optional[List[str]] = None,
                       metadata: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        print(f"开始执行当前组件{kwargs['name']}，run_id: {run_id}, 入参：{inputs}")

    def on_chain_end(self, outputs: Dict[str, Any], *, run_id: UUID, parent_run_id: Optional[UUID] = None,
                     **kwargs: Any) -> Any:
        print(f"结束执行当前组件，run_id: {run_id}, 执行结果：{outputs}, {kwargs}")

# 读取env配置
dotenv.load_dotenv()

# 设置本地模型，不适用深度思考
llm = ChatOllama(base_url="http://192.168.100.17:11434", model="qwen3:8b", reasoning=False)

chinese_prompt = ChatPromptTemplate.from_messages([
    ("system","你是一个专业，请用中文回答"),
    ("human","请介绍下什么是{chinese_name}")
])

chinese_parser = StrOutputParser()


chinses_chain = chinese_prompt | llm | chinese_parser


english_prompt = ChatPromptTemplate.from_messages([
    ("system","你是一个专家，请用英文回答"),
    ("human","请介绍下什么是{english_name}")
    ])

english_parse = StrOutputParser()


english_chain = english_prompt | llm | english_parse

# 设置回调处理类
config = RunnableConfig(callbacks=[CustomCallbackHandler()])

# 创建并行链

parallel_chain = RunnableParallel(
    {
        "chinese": chinses_chain,
        "english": english_chain
    }
)

# 调用符合链
result = parallel_chain.invoke({
    "chinese_name":"马斯克",
    "english_name":"马斯克"
},config)
# parallel_chain.get_graph().print_ascii()


print(result)