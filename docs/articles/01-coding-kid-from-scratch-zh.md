# 从头写 Coding Kid：能用就好

## 下一个字

现在你手上只有一个大语言模型而已，它不是OpenAI帮你做好的可以一直聊天的chatbot，而真的仅仅就是一个坦荡全裸的光溜溜的LLM。

全裸的LLM基本上只会做一件事情，就是文字接龙。具体点讲，就是你丢给他一段我们现在称为prompt的文字，它会做一堆你理解不了的数学，然后帮你预测这段文字的下一个字应该是什么。Well,不能说是下一个字，实际上是下一个token，尤其是英文中一个字常常可以因不同的分词方法而被分词不同的token。但是这对你这种……我是说我这种笨蛋来说太难了，所以我们就理解成预测下一个字算了。

[此处应放个图]

关于中间那一堆数学，怎样算出每个字作为下一个字的概率，怎样调整它，让基于这堆概率输出的结果非常牛逼，这都属于大语言模型的范畴。而基于丢进去一段和预测出来的东西，能做出什么牛逼的事情，广义上大概都算是agent的这部分工作，也是我们比较关心的范畴。

当然，如果它真的只是给你下一个字，那一定难用到爆炸。所以作为一个产品，大家其实会让它连续预测下一个字，一直到它觉得可以停下来，然后整段丢回来给你。

总之上面这件事是任何人都很容易做到的，事实上，如果你去看看你要用的大模型的官方文档，他们大部分甚至会直接把代码给你。你只要充上钱，创建API，就可以一直丢一段话给他，拿一段话回来。

作为我们这整个从头用Python写一个coding agent这个牛逼大项目的超级起点，我们就来实现这个provider。

新建 `src/coding_kid/provider.py`：

```python
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


ModelInput = str | Sequence[Mapping[str, Any]]


@dataclass
class ProviderResponse:
    text: str
    raw: Any


class OpenAIProvider:
    def __init__(self, model: str = "gpt-5.5") -> None:
        self.client = OpenAI()
        self.model = model

    def generate(self, input: ModelInput) -> ProviderResponse:
        response = self.client.responses.create(
            model=self.model,
            input=input,
        )

        return ProviderResponse(
            text=response.output_text,
            raw=response,
        )
```
