## latexmk 配置
## 在 paper/ 目录下直接执行 `latexmk` 即可编译；
## `latexmk -c` 清理中间文件；`latexmk -C` 连同 PDF 一起清理；
## `latexmk -pvc` 进入监听模式（保存即重编）。

# 默认使用 XeLaTeX（中文 + xeCJK 必需）
$pdf_mode = 5;          # 5 = xelatex -> xdv -> pdf

# 编译命令：开启 SyncTeX，便于编辑器正反向跳转
$xelatex = 'xelatex -synctex=1 -interaction=nonstopmode -file-line-error %O %S';

# 中间文件与最终 PDF 均输出到 build/
$out_dir = 'build';
$aux_dir = 'build';

# 监听模式（-pvc）下用系统默认 PDF 阅读器打开
$pdf_previewer = 'open %S';
$preview_continuous_mode = 0;

# 参考文献：biblatex + biber backend（GB/T 7714-2015）
$bibtex_use = 2;        # 即使 .aux 中没引用也运行 biber
