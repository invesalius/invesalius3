

PROG=scnvtk
#IFT_DIR=~/ift
#VTK_DIR=/hd2/lib/VTK


all: _${PROG}.so

_${PROG}.so: ${PROG}.i ${PROG}.cxx
	@echo "Generating wrappers..."
	@swig -c++ -python ${PROG}.i
	@echo "Compiling..."
	@c++ -c ${PROG}.cxx ${PROG}_wrap.cxx -I/usr/include/python2.6 -I${OPF_DIR}/include -I${IFT_DIR}/include -L${IFT_DIR}/lib/ -lift -I${VTK_DIR} -I${VTK_DIR}/Common -I${VTK_DIR}/Utilities -I${VTK_DIR}/VolumeRendering -I${VTK_DIR}/Rendering -I${VTK_DIR}/Utilities/vtkalglib -I${VTK_DIR}/Infovis -I${VTK_DIR}/Geovis -I${VTK_DIR}/Views -I${VTK_DIR}/Hybrid -I${VTK_DIR}/Widgets -I${VTK_DIR}/Rendering/Testing/Cxx -I${VTK_DIR}/IO -I${VTK_DIR}/Imaging -I${VTK_DIR}/Graphics -I${VTK_DIR}/GenericFiltering -I${VTK_DIR}/Filtering -I${VTK_DIR}/Common/Testing/Cxx -I${VTK_DIR}/Utilities/vtklibproj4 -I${VTK_DIR}/Utilities/DICOMParser -I${VTK_DIR}/Utilities/vtkfreetype/include -I${VTK_DIR}/Utilities/vtknetcdf -I${VTK_DIR}/Utilities/vtkexodus2/include -I${VTK_DIR}/Utilities/MaterialLibrary -I${VTK_DIR}/Utilities/verdict -I/usr/include/tcl8.4	-Wno-deprecated
	@echo "Linking..."
	@c++ -shared ${PROG}.o ${PROG}_wrap.o -o _${PROG}.so -L${IFT_DIR}/lib/ -lift #-L${VTK_DIR}/bin -lvtkRendering -lift -lvtkGraphics -lvtkverdict -lvtkImaging -lvtkIO -lvtkFiltering -lvtkCommon -lpthread -lm -lvtkDICOMParser -lvtkNetCDF -lvtkmetaio -lvtksqlite -lvtkpng -lvtktiff -lvtkzlib -lvtkjpeg -lvtkexpat -lvtksys -ldl -lvtkftgl -lvtkfreetype -lGL -lOSMesa -lXt -lSM -lICE -lX11 -lXext 
	@echo "Done."

clean: 
	rm ${PROG}.o ${PROG}.py ${PROG}_wrap.cxx ${PROG}_wrap.o ${PROG}.py _${PROG}.so *.pyc *.obj *.exp *.pyd *.lib *~




