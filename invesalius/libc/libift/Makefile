

PROG=libift
#IFT_DIR=~/ift
#VTK_DIR=/hd2/lib/VTK


all: _${PROG}.so

_${PROG}.so: ${PROG}.i ${PROG}.c
	@echo "Generating wrappers..."
	@swig -python ${PROG}.i
	@echo "Compiling..."
	@gcc -c ${PROG}.c ${PROG}_wrap.c -I/usr/include/python2.6 -I${OPF_DIR}/include -I${IFT_DIR}/include -L${IFT_DIR}/lib/ -lift -Wno-deprecated
	@echo "Linking..."
	@gcc -shared ${PROG}.o ${PROG}_wrap.o -o _${PROG}.so -L${IFT_DIR}/lib/ -lift 
	@echo "Done."


clean: 
	rm ${PROG}.o ${PROG}.py ${PROG}_wrap.c ${PROG}_wrap.o ${PROG}.py _${PROG}.so *.pyc *.obj *.pyd *.exp *.lib *~




