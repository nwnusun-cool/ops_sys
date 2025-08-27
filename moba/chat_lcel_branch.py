from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableBranch
from langchain_ollama import ChatOllama

# 设置本地模型，不使用深度思考
llm = ChatOllama(base_url="http://192.168.100.17:11434", model="qwen3:8b", reasoning=False)

def determine_language(inputs):
    """判断语言种类"""
    query = inputs["query"]
    if "日语" in query:
        return "japanese"
    elif "韩语" in query:
        return "korean"
    elif "藏语" in query:
        return "zangyu"
    else:
        return "english"

# 构建提示词
english_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个英语翻译专家，你叫小英"),
    ("human", "{query}")
])

zangyu_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个藏语翻译专家，你叫小藏"),
    ("human", "{query}")
    ])

japanese_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个日语翻译专家，你叫小日"),
    ("human", "{query}")
])

korean_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个韩语翻译专家，你叫小韩"),
    ("human", "{query}")
])
# 创建字符串输出解析器
parser = StrOutputParser()
# 构建链分支结构，默认分支为汉语
# 创建一个可运行的分支链，根据输入文本的语言类型选择相应的处理流程
# 该链会首先判断输入文本的语言，然后路由到对应的提示词模板、大语言模型和解析器组合

chain = RunnableBranch(
    (lambda x: determine_language(x) == "japanese", japanese_prompt | llm | parser),
    (lambda x: determine_language(x) == "korean", korean_prompt | llm | parser),
    (lambda x: determine_language(x) == "zangyu", zangyu_prompt | llm | parser),
    (english_prompt | llm | parser)
)

# 输出结果
print(f"输出结果：{chain.invoke({'query': '请你用藏语翻译这句话：“你好”'})}")