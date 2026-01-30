<picture class="github-only">
  <source media="(prefers-color-scheme: light)" srcset="https://langchain-ai.github.io/langgraph/static/wordmark_dark.svg">
  <source media="(prefers-color-scheme: dark)" srcset="https://langchain-ai.github.io/langgraph/static/wordmark_light.svg">
  <img alt="LangGraph Logo" src="https://langchain-ai.github.io/langgraph/static/wordmark_dark.svg" width="80%">
</picture>

<div>
<br>
</div>

[![Version](https://img.shields.io/pypi/v/langgraph.svg)](https://pypi.org/project/langgraph/)
[![Downloads](https://static.pepy.tech/badge/langgraph/month)](https://pepy.tech/project/langgraph)
[![Open Issues](https://img.shields.io/github/issues-raw/langchain-ai/langgraph)](https://github.com/langchain-ai/langgraph/issues)
[![Docs](https://img.shields.io/badge/docs-latest-blue)](https://docs.langchain.com/oss/python/langgraph/overview)

LangGraph 是一個低層級的編排框架，用於構建、管理和部署長時間運行、有狀態的代理（agents）。受到包括 Klarna、Replit、Elastic 等在內，正在塑造代理未來的公司所信賴。

## 快速開始

安裝 LangGraph：

```
pip install -U langgraph
```

建立一個簡單的工作流程：

```python
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict


class State(TypedDict):
    text: str


def node_a(state: State) -> dict:
    return {"text": state["text"] + "a"}


def node_b(state: State) -> dict:
    return {"text": state["text"] + "b"}


graph = StateGraph(State)
graph.add_node("node_a", node_a)
graph.add_node("node_b", node_b)
graph.add_edge(START, "node_a")
graph.add_edge("node_a", "node_b")

print(graph.compile().invoke({"text": ""}))
# {'text': 'ab'}
```

開始使用 [LangGraph 快速開始指南](https://docs.langchain.com/oss/python/langgraph/quickstart)。

若要使用 LangChain 的 `create_agent`（基於 LangGraph 構建）快速建立代理，請參閱 [LangChain 代理文件](https://docs.langchain.com/oss/python/langchain/agents)。

## 核心優勢

LangGraph 為*任何*長時間運行、有狀態的工作流程或代理提供低層級的支援基礎設施。LangGraph 不會抽象化提示詞或架構，並提供以下核心優勢：

- [持久化執行](https://docs.langchain.com/oss/python/langgraph/durable-execution)：構建能夠在失敗後持續運行並可長時間運行的代理，自動從中斷處精確恢復。
- [人機協作](https://docs.langchain.com/oss/python/langgraph/interrupts)：透過在執行過程中的任何時間點檢查和修改代理狀態，無縫整合人工監督。
- [完整記憶](https://docs.langchain.com/oss/python/langgraph/memory)：建立真正有狀態的代理，同時具備用於持續推理的短期工作記憶和跨會話的長期持久記憶。
- [使用 LangSmith 進行除錯](http://www.langchain.com/langsmith)：透過可視化工具深入了解複雜的代理行為，這些工具可以追蹤執行路徑、捕獲狀態轉換，並提供詳細的運行時指標。
- [生產就緒的部署](https://docs.langchain.com/langsmith/app-development)：使用專為處理有狀態、長時間運行工作流程的獨特挑戰而設計的可擴展基礎設施，自信地部署複雜的代理系統。

## LangGraph 生態系統

雖然 LangGraph 可以獨立使用，但它也能與任何 LangChain 產品無縫整合，為開發者提供構建代理的完整工具套件。為了改善您的 LLM 應用程式開發，可以將 LangGraph 與以下工具配對使用：

- [LangSmith](http://www.langchain.com/langsmith) — 有助於代理評估和可觀測性。除錯表現不佳的 LLM 應用程式運行、評估代理軌跡、在生產環境中獲得可見性，並隨著時間推移改善效能。
- [LangSmith Deployment](https://docs.langchain.com/langsmith/deployments) — 使用專為長時間運行、有狀態工作流程而構建的部署平台，輕鬆部署和擴展代理。在團隊間發現、重用、配置和共享代理 — 並在 [LangGraph Studio](https://docs.langchain.com/oss/python/langgraph/studio) 中使用視覺化原型快速迭代。
- [LangChain](https://docs.langchain.com/oss/python/langchain/overview) – 提供整合和可組合的組件，以簡化 LLM 應用程式開發。

> [!NOTE]
> 正在尋找 LangGraph 的 JS 版本？請參閱 [JS 儲存庫](https://github.com/langchain-ai/langgraphjs) 和 [JS 文件](https://docs.langchain.com/oss/javascript/langgraph/overview)。

## 其他資源

- [指南](https://docs.langchain.com/oss/python/langgraph/overview)：針對串流、添加記憶和持久化、設計模式（例如分支、子圖等）等主題的快速、可操作的程式碼片段。
- [參考文件](https://reference.langchain.com/python/langgraph/)：關於核心類別、方法、如何使用圖和檢查點 API，以及高層級預構建組件的詳細參考。
- [範例](https://docs.langchain.com/oss/python/langgraph/agentic-rag)：開始使用 LangGraph 的引導式範例。
- [LangChain 論壇](https://forum.langchain.com/)：與社群聯繫並分享您的所有技術問題、想法和反饋。
- [LangChain 學院](https://academy.langchain.com/courses/intro-to-langgraph)：在我們免費的結構化課程中學習 LangGraph 的基礎知識。
- [案例研究](https://www.langchain.com/built-with-langgraph)：了解業界領導者如何使用 LangGraph 大規模交付 AI 應用程式。

## 致謝

LangGraph 受到 [Pregel](https://research.google/pubs/pub37252/) 和 [Apache Beam](https://beam.apache.org/) 的啟發。公開介面從 [NetworkX](https://networkx.org/documentation/latest/) 中汲取靈感。LangGraph 由 LangChain Inc（LangChain 的創建者）構建，但可以在不使用 LangChain 的情況下使用。

