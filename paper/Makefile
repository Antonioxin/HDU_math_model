## 论文编译入口
## 用法：
##   make            # 一次性编译，输出 build/main.pdf
##   make watch      # 监听模式，保存 .tex 自动重编并刷新预览
##   make open       # 打开当前编译出的 PDF（macOS）
##   make clean      # 清理中间文件（保留 PDF）
##   make distclean  # 连同 PDF 一起清理

MAIN := main
BUILD := build
PDF  := $(BUILD)/$(MAIN).pdf

.PHONY: all watch open clean distclean

all: $(PDF)

$(PDF): $(MAIN).tex $(wildcard sections/*.tex) references.bib
	latexmk $(MAIN).tex

watch:
	latexmk -pvc $(MAIN).tex

open: $(PDF)
	open "$(PDF)"

clean:
	latexmk -c

distclean:
	latexmk -C
	rm -rf $(BUILD)
