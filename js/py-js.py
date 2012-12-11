#!/usr/bin/env python

import os
from js.execution import JsException
from pypy.rlib.objectmodel import enforceargs
from pypy.rlib.parsing.parsing import ParseError
from pypy.rlib.parsing.deterministic import LexerError


def main(argv):
    opts, files = parse_args(argv)

    try:
        run(files, opts)
    except SystemExit:
        printmessage(u"\n")

    return 0


def run(files, opts):
    from js.interpreter import Interpreter

    interactive = len(files) == 0
    inspect = opts.get('inspect', False)

    interp = Interpreter(opts)

    for f in files:
        try:
            interp.run_file(f)
        except JsException as e:
            printerrormessage(unicode(f), e._msg())
            raise SystemExit

    if inspect or interactive:
        repl(interp)


@enforceargs(unicode, unicode)
def printerrormessage(filename, message):
    printmessage(u"ERROR in %s: %s\n" % (filename, message))


def repl(interpreter):
    filename = u'<stdin>'
    while True:
        printmessage(u'js> ')
        line = readline()

        try:
            result = interpreter.run_src(line)
            result_string = result.to_string()
            printmessage(u"%s\n" % (result_string))
        except ParseError as exc:
            printsyntaxerror(filename, exc, line)
            continue
        except LexerError as e:
            printlexererror(filename, e, line)
            continue
        except JsException as e:
            printerrormessage(filename, e._msg())
            continue


# https://bitbucket.org/cfbolz/pyrolog/src/f18f2ccc23a4/prolog/interpreter/translatedmain.py
@enforceargs(unicode)
def printmessage(msg):
    from js.runistr import encode_unicode_utf8
    os.write(1, encode_unicode_utf8(msg))


def print_sourcepos(filename, source_pos, source):
    marker_indent = u' ' * source_pos.columnno
    error_lineno = source_pos.lineno
    error_line = (source.splitlines())[error_lineno]
    printmessage(u'Syntax Error in: %s:%d\n' % (unicode(filename), error_lineno))
    printmessage(u'%s\n' % (unicode(error_line)))
    printmessage(u'%s^\n' % (marker_indent))


def printlexererror(filename, exc, source):
    print_sourcepos(filename, exc.source_pos, source)


def printsyntaxerror(filename, exc, source):
    # XXX format syntax errors nicier
    print_sourcepos(filename, exc.source_pos, source)
    error = exc.errorinformation.failure_reasons
    printmessage(u'Error: %s\n' % (unicode(str(error))))


# https://bitbucket.org/cfbolz/pyrolog/src/f18f2ccc23a4/prolog/interpreter/translatedmain.py
def readline():
    result = []
    while True:
        s = os.read(0, 1)
        result.append(s)
        if s == "\n":
            break
        if s == '':
            if len(result) > 1:
                break
            raise SystemExit
    return "".join(result)


def _parse_bool_arg(arg_name, argv):
    for i in xrange(len(argv)):
        if argv[i] == arg_name:
            del(argv[i])
            return True
    return False


def parse_args(argv):
    opts = {}

    opts['debug'] = _parse_bool_arg('-d', argv) or _parse_bool_arg('--debug', argv)
    opts['inspect'] = _parse_bool_arg('-i', argv) or _parse_bool_arg('--inspect', argv)
    opts['no-exception-jseval'] = _parse_bool_arg('--no-exception-jseval', argv)

    del(argv[0])

    return opts, argv


if __name__ == '__main__':
    import sys
    main(sys.argv)


# _____ Define and setup target ___
def target(driver, args):
    driver.exe_name = 'py-js'
    return entry_point, None


def jitpolicy(driver):
    from pypy.jit.codewriter.policy import JitPolicy
    return JitPolicy()


def entry_point(argv):
    return main(argv)
