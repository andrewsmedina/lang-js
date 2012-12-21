from js.object_space import w_return, hide_on_translate
#from pypy.rlib import jit


def setup_builtins(global_object, overwrite_eval=False):
    from js.builtins import put_native_function

    put_native_function(global_object, u'load', js_load)
    put_native_function(global_object, u'debug', js_debug)

    ## the tests expect eval to return "error" on an exception
    if overwrite_eval is True:
        from js.builtins import put_intimate_function
        global_object._del_prop(u'eval')
        put_intimate_function(global_object, u'eval', overriden_eval, configurable=False, params=[u'x'])

    put_native_function(global_object, u'trace', js_trace)


@w_return
def js_load(this, args):
    from js.object_space import object_space
    from js.interpreter import load_file
    filename = args[0].to_string()
    src = load_file(str(filename))
    object_space.interpreter.run_src(src)


@w_return
@hide_on_translate
def js_trace(this, args):
    import pdb
    pdb.set_trace()


@w_return
def js_debug(this, args):
    from js.object_space import object_space
    config = object_space.interpreter.config
    config.debug = not config.debug
    return config.debug


def overriden_eval(ctx):
    from js.builtins_global import js_eval
    from js.execution import JsException
    from js.completion import NormalCompletion
    from js.jsobj import _w
    try:
        return js_eval(ctx)
    except JsException:
        return NormalCompletion(value=_w("error"))
