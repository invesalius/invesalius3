all: 
	pdflatex manual_pt_BR
	bibtex manual_pt_BR
	pdflatex manual_pt_BR
	pdflatex manual_pt_BR
clean: 
	rm -f *.dvi *.log *.toc *.aux *.bbl *.blg *.loa *.los *.out *.cb 

cleanall:
	rm -f manual_pt_BR.pdf *.dvi *.log *.toc *.aux *.bbl *.blg *.loa *.los *.out *.cb

move:
	mv -f manual_pt_BR.pdf ../user_guide_pt_BR.pdf
