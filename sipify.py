# ===========================================================================
#
#   Filename: sipify.py
#
#   Copyright (c) 2015 Lamond Lab
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0.txt
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ===========================================================================

import os
from sys import exit
from io import BytesIO, StringIO
from datetime import datetime
from CppHeaderParser import CppHeader, CppParseError

QT_VERSION=0x54000

def createSIP(headerFile, sipDir, headerTemplate):
    print("Processing file: ", headerFile)

    def checkRanges(lineNumber):
        for r in skip_ranges:
            if r[0]<=lineNumber<=r[1]:
                return True
        return False

    def createMethods(s, methods, includeConstructors=True):
        for method in methods:
            if method['constructor'] and not includeConstructors: continue

            if checkRanges(method['line_number']):
                print("SKIP:", method['name'], method['line_number'])
                continue

            line="  "
            if method['virtual']: line+="virtual "
            if method['explicit']: line+="explicit "
            if not (method['constructor'] or method['destructor']):
                rtnType=method['rtnType'].replace('inline ','')               
                line+=rtnType
                if not rtnType.endswith('*'): line+=' '
            if method['destructor']: line+='~'
            line+=method['name']+'('

            parameters=[]
            for param in method['parameters']:
                param_str=""
                if param['constant']: param_str+='const '

                paramType=param['raw_type']
                if paramType.startswith('::'): paramType=paramType[2:]
                param_str+=paramType
                if param['pointer']: param_str+=" *"
                elif param['reference']: param_str+=" &"
                else: param_str+=" "
                param_str+=param['name']

                if method['constructor'] and 'parent' in param['name'].lower():
                    param_str+=" /TransferThis/"

                if 'defaultValue' in param: param_str+=' = '+param['defaultValue']
                parameters.append(param_str)

            line+=", ".join(parameters)
            line+=")"
            if method['const']: line+=" const"

            line+=';\n'
            s.write(line)

        s.write("\n")
    
    headerFileStr=open(headerFile,'r').read()

    ### Pre-Parse
    ### This is kind of like Qt's MOC - we're basically removing/replacing
    ### all of Qt's macro's to make the code straight C++.

    headerFileStr=headerFileStr.replace("Qt::UserRole","32")

    ### We *really* don't need the following
    headerFileStr=headerFileStr.replace('Q_OBJECT','')
    headerFileStr=headerFileStr.replace('Q_INVOKABLE','')

    for macro in ('Q_PRIVATE_SLOT', 'Q_PROPERTY', 'Q_ENUMS', 'Q_FLAGS', 'Q_DECLARE_PUBLIC'):
        start=headerFileStr.find('{}('.format(macro))
        declarations=[]
        while start>=0:
            end=headerFileStr.find('\n', start)+1
            declarations.append(headerFileStr[start:end])
            start=headerFileStr.find('{}('.format(macro), end)
        for declaration in declarations: headerFileStr=headerFileStr.replace(declaration,'')

    ### Remember which enums are declared via Q_DECLARE_FLAGS for later and then remove
    ### the declaration.
    declare_flags={}
    start=headerFileStr.find("Q_DECLARE_FLAGS(")
    declarations=[]
    while start>=0:
        end=headerFileStr.find(")", start)+1
        declarations.append(headerFileStr[start:end])
        declareFlags=headerFileStr[start:end].replace("Q_DECLARE_FLAGS(",'').replace(')','')
        flags,enum=declareFlags.replace(' ','').split(',')
        declare_flags[enum]=flags
        start=headerFileStr.find("Q_DECLARE_FLAGS(", end)
    for declaration in declarations: headerFileStr=headerFileStr.replace(declaration,'')

    ### Remember which enums have operators declared via Q_DECLARE_OPERATORS_FOR_FLAGS
    ### for later and then remove the declaration.
    declare_operators={}
    start=headerFileStr.find("Q_DECLARE_OPERATORS_FOR_FLAGS(")
    declarations=[]
    while start>=0:
        end=headerFileStr.find(")", start)+1
        declarations.append(headerFileStr[start:end])
        declareOperators=headerFileStr[start:end].replace("Q_DECLARE_OPERATORS_FOR_FLAGS(",'').replace(')','')
        ns,flags=declareOperators.replace(' ','').strip().split('::')
        for enum,f in declare_flags.items():
            if f==flags: break
        else: raise Exception(ns,flags)
        declare_operators[ns]=enum
        start=headerFileStr.find("Q_DECLARE_OPERATORS_FOR_FLAGS(", end)
    for declaration in declarations: headerFileStr=headerFileStr.replace(declaration,'')

    ### Remember which classes are decalred as private via Q_DECLARE_PRIVATE and then
    ### remove the declaration
    declare_private=[]
    start=headerFileStr.find("Q_DECLARE_PRIVATE(")
    declarations=[]
    while start>=0:
        end=headerFileStr.find(")", start)+1
        declarations.append(headerFileStr[start:end])
        declarePrivate=headerFileStr[start:end].replace("Q_DECLARE_PRIVATE(",'').replace(')','')
        declare_private.append(declarePrivate)
        start=headerFileStr.find("Q_DECLARE_PRIVATE(", end)
    for declaration in declarations: headerFileStr=headerFileStr.replace(declaration,'')

    ### Remember which classes have copying disabled via Q_DECLARE_COPY and then
    ### remove the declaration    
    disable_copy=[]
    start=headerFileStr.find("Q_DISABLE_COPY(")
    declarations=[]
    while start>=0:
        end=headerFileStr.find(")", start)+1
        declarations.append(headerFileStr[start:end])
        disableCopy=headerFileStr[start:end].replace("Q_DISABLE_COPY(",'').replace(')','')
        disable_copy.append(disableCopy)
        start=headerFileStr.find("Q_DISABLE_COPY(", end)
    for declaration in declarations: headerFileStr=headerFileStr.replace(declaration,'')

    ### Read header file as lines rather than single string
    #with open(headerFile, 'r') as f:
    #    headerLines=f.readlines()
    headerLines=headerFileStr.split('\n')

    ### Make a list of export symbols and exported objects...
    exports=[]
    export_symbols=[]
    for line in headerLines:
        if '_EXPORT' not in line or line.strip().startswith('//'): continue

        pieces=line.strip().replace(":",'').replace('{','').split(' ')
        assert '_EXPORT' in  pieces[1]
        export_symbols.append(pieces[1])
        exports.append(pieces[2])

    ### ... then remove symbols to simplify parsing
    for sym in set(export_symbols):
        headerFileStr=headerFileStr.replace(sym, '')

    ### Parse header
    try: cppHeader=CppHeader(headerFileStr, argType="string")    
    except CppHeaderParser.CppParseError as e:
        print(e)
        exit(1)

    ### 'Process' pre-processor macros...
    conditionals=cppHeader.conditionals[1:-1]
    _conditionals=[]
    for n,line in enumerate(headerLines):
        if not line.strip().startswith(('#if','#else','#endif')): continue
        if line.strip() not in conditionals: continue
              
        try:assert line.strip()==conditionals[0]
        except AssertionError:
            print("CONDITIONALS:",n, line.strip(), conditionals)    
            print (headerFileStr)
            raise

        _conditionals.append((conditionals.pop(0),n+1))

    defines=['USE_QFILEDIALOG_OPTIONS']
    skip=True
    start,stop=None,None
    skip_ranges=[]
    for condition,n in _conditionals:
        if condition.startswith('#if'):
            pieces=condition.strip().split()
            cond,name=pieces[:2]

            check=False
            if name=='QT_VERSION':
                assert len(pieces)>=4
                operator,version=pieces[2:4]
                assert operator in ('>', '>=', '<', '<=')
                if 'QT_VERSION_CHECK' in version:
                    version=''.join(pieces[3:])
                    version=version.replace('QT_VERSION_CHECK(','').replace(')','')
                    version='0x'+''.join(version.split(','))+'00'
                check=eval("{}{}{}".format(QT_VERSION, operator, version))

            if (name in defines or check) and cond=='#ifdef': skip=False
            elif (name in defines and cond=='#ifndef'): skip=True
            if skip: start=n

        elif condition.startswith('#else'):
            skip=not skip
            if skip: start=n
            else: stop=n

        elif condition.startswith('#endif'):
            if skip: stop=n
            if not skip: skip=True
        else: raise Exception

        if start and stop:
            skip_ranges.append((start,stop))
            start,stop=None,None

    sipFile=os.path.splitext(os.path.split(headerFile)[1])[0]+'.sip'
    sipFile=os.path.abspath(os.path.join(sipDir, sipFile))
    sipIncludes=[]
    exported_objects=[]

    s=StringIO()

    ### NAMESPACES
    namespace_funtions={}
    for function in cppHeader.functions:
        if not len(function['namespace']): continue

        namespace=function['namespace'].replace(':','')
        namespace_funtions.setdefault(namespace, []).append(function)

    for namespace, functions in namespace_funtions.items():
        print("  namespace: ", namespace)
        s.write('namespace {} {{\n\n'.format(namespace))

        ## TYPEHEADERCODE
        s.write("%TypeHeaderCode\n")
        s.write("#include \"{}\"\n".format(os.path.split(headerFile)[1]))
        s.write("%End\n\n")

        createMethods(s, functions)

        s.write('};\n\n')

    ### CLASSSES
    for className,classObject in cppHeader.classes.items():
        if not className in exports: continue
        exported_objects.append(className)
        print("  object: ", className)

        ## DECLARATION
        declarationMethod=classObject['declaration_method']
        declarationLine="{} {} ".format(declarationMethod, className)
        inherits=classObject['inherits']
        if len(inherits):
            declarationLine+=": "

            inheritStrings=[]
            for inherit in inherits:
                inheritStrings.append(inherit['access']+" "+inherit['class'])
                if not inherit['class'].startswith('Q'): sipIncludes.append(inherit['class'])

            declarationLine+=', '.join(inheritStrings)

        declarationLine+=" {"
        s.write(declarationLine)
        s.write('\n\n')

        ## TYPEHEADERCODE
        s.write("%TypeHeaderCode\n")
        s.write("#include \"{}\"\n".format(os.path.split(headerFile)[1]))
        s.write("%End\n\n")

        ## PUBLIC
        s.write("public:\n")
        for enum in classObject['enums']['public']:
            if checkRanges(enum['line_number']):
                print("SKIP:", enum.get('name','[ENUM]'), enum['line_number'])
                continue
            s.write("  enum {} {{\n".format(enum.get('name','')))
            for value in enum['values']:
                _value=str(value['value'])
                if '+' in _value or '|' in _value:
                    try:_value=eval(_value)
                    except NameError:
                        assert '|' in _value
                        bits=_value.replace(' ','').split('|')
                        bits_vals=[]
                        for v in enum['values']:
                            if v['name'] in bits: bits_vals.append(str(v['value']))
                        _value=eval('|'.join(bits_vals))

                s.write("    {}={},\n".format(value['name'],_value))

            s.write("  };\n")

            if enum.get('name',None) in declare_flags:
                s.write("  typedef QFlags<{0}::{1}> {2};\n".format(className, enum['name'], declare_flags[enum['name']]))
            s.write('\n')

        methods=classObject['methods']['public']
        createMethods(s, methods)

        ## PUBLIC SLOTS
        methods=classObject['methods']['public slots']+classObject['methods']['public Q_SLOTS']
        if len(methods):
            s.write("public slots:\n")
            createMethods(s, methods)

        ## PROTECTED
        enums=classObject['enums']['protected']        
        methods=classObject['methods']['protected']
        if len(methods) or len(enums):
            s.write("protected:\n")

            for enum in enums:
                s.write("  enum {} {{\n".format(enum.get('name','')))
                for value in enum['values']:
                    _value=str(value['value'])
                    if '+' in _value or '|' in _value:
                        try:_value=eval(_value)
                        except NameError:
                            assert '|' in _value
                            bits=_value.replace(' ','').split('|')
                            bits_vals=[]
                            for v in enum['values']:
                                if v['name'] in bits: bits_vals.append(str(v['value']))
                            _value=eval('|'.join(bits_vals))

                    s.write("    {}={},\n".format(value['name'],_value))

                s.write("  };\n")

                if enum.get('name',None) in declare_flags:
                    s.write("  typedef QFlags<{0}::{1}> {2};\n".format(className, enum['name'], declare_flags[enum['name']]))
                s.write('\n')

            createMethods(s, methods, includeConstructors=False)

        ## PROTECTED SLOTS
        methods=classObject['methods']['protected slots']+classObject['methods']['protected Q_SLOTS']
        if len(methods):
            s.write("protected slots:\n")
            createMethods(s, methods)

        ## SIGNALS
        methods=classObject['methods']['signals']+classObject['methods']['Q_SIGNALS']
        if len(methods):
            s.write("signals:\n")
            createMethods(s, methods)

        if className in declare_private or className in disable_copy:
            s.write("private:\n")
            if className in declare_private:
                s.write('  {0}(const {0} &);\n'.format(className))
            if className in disable_copy:
                s.write('  {0} &operator=(const {0} &);\n'.format(className))

        s.write("\n};\n\n")

    # if len(declare_operators):
    #     for ns,enum in declare_operators.items():
    #         s.write("\nQFlags<{0}::{1}> operator|({0}::{1} f1, QFlags<{0}::{1}> f2);".format(ns,enum))

    s.seek(0)
    sipFileStr=s.read().replace("Qt : : ", "Qt::")
    sipFileStr=sipFileStr.replace(' : : ', '::')
    if not len(sipFileStr) or sipFileStr.isspace(): return

    with open(sipFile,'w') as ss:
        ss.write(headerTemplate.format(file_name=os.path.split(sipFile)[1]))
        ss.write('\n\n')

        if len(sipIncludes):
            for include in sipIncludes:
                if include in exported_objects: continue
                ss.write('%Include {}.sip\n'.format(include))
            ss.write('\n')

        ss.write(sipFileStr)

if __name__=="__main__":
    from argparse import ArgumentParser

    parser=ArgumentParser(description="Generate SIP files from C++ headers.")
    parser.add_argument(
        '-i','--input',
        dest="input",
        type=str,
        default=".",
        help="Directory containing C++ header input files."
    )
    parser.add_argument(
        '-o','--output',
        dest="output",
        type=str,
        default='.',
        help="Directory to contain SIP output files."
    )
    parser.add_argument(
        '--header',
        dest="header",
        type=str,
        default=None,
        help="Name of file containing header template."
    )
    parser.add_argument(
        '--lib_name',
        dest="lib_name",
        type=str,
        default="",
        help="Library name."
    )    
    parser.add_argument(
        '--year',
        dest="year",
        type=str,
        default=str(datetime.now().year),
        help="Copyright year."
    )
    parser.add_argument(
        '--name',
        dest="name",
        type=str,
        default="",
        help="Copyright name."
    )    
    args=parser.parse_args()

    headerTemplate=None
    if args.header:
        headerTemplateFile=os.path.abspath(args.header)
        if os.path.exists(headerTemplateFile):
            headerTemplate=open(headerTemplateFile,'r').read()
            headerTemplate=headerTemplate.format(
                lib_name=args.lib_name,
                copy_year=args.year,
                copy_name=args.name,
                file_name='{file_name}'
            )

    input_dir=os.path.abspath(args.input)
    if not (os.path.exists(input_dir) and os.path.isdir(input_dir)): raise Exception

    output_dir=os.path.abspath(args.output)
    if not (os.path.exists(output_dir)):
        os.mkdir(output_dir)

    for f in os.listdir(input_dir):
        name,ext=os.path.splitext(f)
        if ext!='.h' or name.endswith('_p'): continue

        if f=="ctkWidgets.h": continue
        createSIP(os.path.join(input_dir,f), output_dir, headerTemplate)

    print("Removing empty files:")
    for f in os.listdir(output_dir):
        fpath=os.path.join(output_dir,f)
        if os.stat(fpath).st_size==0:
            print("\t{}".format(f))
            os.remove(fpath)

    for f in os.listdir(output_dir):
        name,ext=os.path.splitext(f)
        if ext!='.sip': continue

        print("%Include {}".format(f))