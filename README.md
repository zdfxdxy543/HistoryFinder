# HistoryFinder

HistoryFinder 是一个程序化历史调查游戏原型。游戏先模拟地理、聚落、人物、贸易、战争、宗教与知识传播，再让玩家进入生成后的世界，通过现场证据、文书、图书、遗址和 NPC 证词重建过去。

同一个世界种子会生成稳定的世界与调查内容。玩家看到的是可观察信息，而不是模拟器内部保存的完整真相。

## 当前功能

- 程序化世界地理：生物群系、山地、湖泊、河流与斜向水系。
- 聚落历史模拟：人口、经济、政治关系、统治者、战争、灾害和自然建城。
- 世界与当地两级地图：聚落、废墟、荒野、道路、桥梁及跨区域旅行。
- 历史遗址：农庄、旅店、矿场、林场、哨塔、墓园等多格建筑。
- 动态荒野：旅行队伍、露营地生命周期、野生动物和活动痕迹。
- 历史调查：搜索、检查、阅读、咨询、证物比较、冲突记录和调查游记。
- 统一文献系统：普通馆藏与历史文本共享文献身份、阅读状态和损坏展示；普通馆藏可主动登记为调查资料。
- NPC 系统：居民、知情人、访客、幸存者和荒野建筑工作人员。
- 像素视觉：证物外观和稳定生成的 NPC 对话肖像。
- 本地时间与环境：昼夜、天气、能见度和 NPC 日程。
- 可扩展新手教程与移动端屏幕控制。

## 快速启动

### Windows

1. 安装 Python 3.10 或更高版本。当前开发环境使用 Python 3.12。
2. 在仓库根目录安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. 双击 `start_game.bat`，或者在 PowerShell 中运行：

   ```powershell
   .\start_game.bat
   ```

启动脚本会检查 Python、按需构建前端、启动本地服务器并打开浏览器。默认地址为：

<http://127.0.0.1:8765/play/>

如果服务器已经运行，再次执行脚本只会打开游戏页面。

### 手动启动

已存在 `player/dist` 时，可以直接启动后端：

```powershell
python -m viewer.server --host 127.0.0.1 --port 8765
```

随后访问 <http://127.0.0.1:8765/play/>。

服务器仅设计为本地开发和试玩服务，没有身份验证，不应直接暴露到公网。

## 基本操作

| 操作 | 键盘 | 触屏或鼠标 |
| --- | --- | --- |
| 移动 | 方向键或 `WASD`，长按可连续移动 | 屏幕方向按钮 |
| 移动速度 | 在当地地图下方切换行走或奔跑 | 同左 |
| 互动 | `E` 或空格 | 互动按钮或调查面板命令 |
| 选择目标 | 点击地图对象 | 点击地图对象 |
| 世界/当地地图 | 顶部地图切换 | 顶部地图切换 |
| 等待十分钟 | 顶部沙漏按钮 | 顶部沙漏按钮 |
| 新手教程 | 顶部问号按钮 | 顶部问号按钮 |

常规调查流程：

1. 在当地地图寻找存储设施、证据、人物或荒野目标。
2. 移动到目标相邻格并选择目标。
3. 搜索容器，发现其中保存的证物。
4. 检查证物后阅读文字，或把证物出示给知情人。
5. 比较不同来源，并在“游记”中查看观察、证词、推断和冲突。
6. 切换到世界地图，前往其他聚落、遗址或荒野区域继续调查。

普通馆藏与历史文献使用不同的内容来源：前者由馆藏主题生成，后者仍由模拟历史事件和来源关系生成。两者共享文献目录字段、持久正文、载体损坏与游记展示。普通馆藏只有在阅读后主动登记，才会进入游记的文献清单；登记不会把它转换成历史证物，也不会虚构事件关联。

世界种子和模拟年数可以在页面顶部调整。重新生成会创建一个新的内存会话。

行走每格消耗 1 分钟，奔跑每格消耗 30 秒。NPC 仍按完整分钟推进日程。

## 调试选项

浏览器界面的终端按钮可以输入调试码：

```text
HF-VISION
```

该调试码会解锁全图视野开关。它只影响玩家能见度，不改变模拟世界。

## 前端开发

前端位于 `player/`，使用 React、TypeScript、Vite 和 Phaser。

```powershell
cd player
npm install
npm run build
```

构建产物会写入 `player/dist`，并由 Python 服务器通过 `/play/` 提供。修改前端后需要重新构建，再刷新浏览器。

## 构建 Windows Release

安装 PyInstaller 后执行：

```powershell
python -m pip install pyinstaller
.\build_release.bat
```

脚本会重新构建前端、生成 one-folder EXE，并输出：

```text
release/HistoryFinder-v0.1.0-windows-x64/
release/HistoryFinder-v0.1.0-windows-x64.zip
```

Release 中的 `HistoryFinder.exe` 不要求玩家安装 Python、Node.js 或 npm。启动后会运行本地服务器并自动打开浏览器；关闭服务器窗口即可退出。

## 命令行模式

项目仍保留文字 REPL 入口：

```powershell
python main.py --seed 42 --years 100 --no-llm
```

常用参数：

- `--seed`：世界种子。
- `--years`：模拟年数。
- `--no-llm`：禁用本地 LLM，使用确定性模板文本。
- `--stats`：生成世界统计后退出。
- `--debug-causes`：输出历史事件的触发因素。
- `--model`：指定本地 GGUF 模型路径。

本地 LLM 完全可选。模型缺失或 `llama-cpp-python` 不可用时，叙事系统会自动退回模板模式；浏览器版的主要玩法不依赖模型文件。

## 测试

安装 pytest 后运行：

```powershell
python -m pip install pytest
python -m pytest -q
```

也可以只运行与玩家界面和地图相关的测试：

```powershell
python -m pytest -q tests/test_player_session.py tests/test_world_cell_maps.py tests/test_historical_sites.py
```

前端类型检查与正式构建：

```powershell
cd player
npm run build
```

当前完整 Python 测试套件有一个已知的存储分类失败：`tests/test_storage.py::test_documents_are_sorted_into_domain_specific_collections`。问题是部分建城文书仍被保存在 `field_site`，而测试期望 `administrative_archive`；它不影响游戏启动或本 README 所述的操作流程。

## 项目结构

```text
HistoryFinder/
|- simulation/   世界状态、地理、人物、事件、证据、图书与历史遗址
|- game/         玩家会话、调查规则、当地地图、时间及像素视觉参数
|- narrative/    叙事模板、证据描述和可选本地 LLM 接口
|- viewer/       本地 HTTP 服务、API 和世界查看数据
|- player/       React + Phaser 浏览器客户端及构建产物
|- tests/        模拟、序列化、调查和地图测试
|- data/         本地世界、缓存与可选模型位置
|- main.py       文字 REPL 入口
`- start_game.bat Windows 快速启动脚本
```

## 设计原则

- **确定性**：相同种子与输入应产生相同的世界、文本和像素外观。
- **历史先于叙事**：事件、记录、实物和口述信息分别生成并保留来源关系。
- **玩家信息隔离**：界面只返回角色能够观察或获知的信息，隐藏模拟真相不会直接泄露。
- **证据可能不完整**：文本会磨损、缺页或被毁，证词也可能受立场、知识和传播过程影响。
- **地点持续变化**：聚落、道路、建筑、营地、NPC 与证据会随历史和本地时间改变。

## 当前限制

- 浏览器会话保存在服务器内存中；关闭服务器后不会恢复当前玩家进度。
- 世界生成和完整测试会执行大量模拟，较大的年数可能需要等待。
- 前端生产包仍较大，Vite 构建会给出代码块大小警告。
- 项目仍处于原型阶段，存档格式和玩法接口可能继续调整。
