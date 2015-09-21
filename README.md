# sipify
A script developed to assist in the creation of SIP descriptor files used to generate python bindings for C++ code.

This script was actually developed to help create the bindings for [PyCTK](http://github.com/lamondlab/pyctk 'PyCTK'). It will ***NOT*** generate working bindings out of the box (you will need to hand fettle the output), however it will do 90% of the boring, repetitive work allowing you to focus on the difficult, specific and/or bespoke bits.

The script depends on a tweaked version of [CppHeaderParser](https://pypi.python.org/pypi/CppHeaderParser/ 'CppHeaderParser') that has been altered to deal with certain Qt specific features/eccentricities and is included here. It should be installed as per the original instructions.
