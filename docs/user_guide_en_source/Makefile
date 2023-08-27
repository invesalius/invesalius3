all: 
	pdflatex user_guide_en
	bibtex user_guide_en
	pdflatex user_guide_en
	pdflatex user_guide_en
clean: 
	rm -f *.dvi *.log *.toc *.aux *.bbl *.blg *.loa *.los *.out *.cb 

cleanall:
	rm -f user_guide_en.pdf *.dvi *.log *.toc *.aux *.bbl *.blg *.loa *.los *.out *.cb

move:
	mv -f user_guide_en.pdf ../user_guide_en.pdf
