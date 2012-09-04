from js.jsobj import _w


class JsBaseFunction(object):
    eval_code = False
    function_code = False
    configurable_bindings = False
    strict = False

    def run(self, ctx):
        raise NotImplementedError

    def estimated_stack_size(self):
        return 2

    def to_string(self):
        return u'function() {}'

    def variables(self):
        return []

    def functions(self):
        return []

    #def index_for_symbol(self, symbol):
        #return None

    #def symbols(self):
        #return []

    #def symbol_for_index(self, index):
        #return None

    def params(self):
        return []

    def name(self):
        return '_unnamed_'

    def is_eval_code(self):
        return False

    def is_function_code(self):
        return False


class JsNativeFunction(JsBaseFunction):
    def __init__(self, function, name=u''):
        self._name_ = name
        self._function_ = function

    def name(self):
        return self._name_

    def run(self, ctx):
        from js.completion import ReturnCompletion

        args = ctx.argv()
        this = ctx.this_binding()
        res = self._function_(this, args)
        w_res = _w(res)
        compl = ReturnCompletion(value=w_res)
        return compl

    def to_string(self):
        name = self.name()
        if name is not None:
            return u'function %s() { [native code] }' % (name, )
        else:
            return u'function () { [native code] }'


class JsIntimateFunction(JsNativeFunction):
    def __init__(self, function, name=u''):
        self._name_ = name
        self._intimate_function_ = function

    def run(self, ctx):
        from js.completion import Completion
        compl = self._intimate_function_(ctx)
        assert isinstance(compl, Completion)
        return compl


class JsExecutableCode(JsBaseFunction):
    def __init__(self, js_code):
        from js.jscode import JsCode
        assert isinstance(js_code, JsCode)
        self._js_code_ = js_code
        self._stack_size_ = js_code.estimated_stack_size()

    def estimated_stack_size(self):
        return self._stack_size_

    def get_js_code(self):
        from js.jscode import JsCode
        assert isinstance(self._js_code_, JsCode)
        return self._js_code_

    def run(self, ctx):
        code = self.get_js_code()
        result = code.run(ctx)
        return result

    def variables(self):
        code = self.get_js_code()
        return code.variables()

    def functions(self):
        code = self.get_js_code()
        return code.functions()

    def params(self):
        code = self.get_js_code()
        return code.params()

    def name(self):
        return u'_unnamed_'

    def to_string(self):
        name = self.name()
        if name is not None:
            return u'function %s() { }' % (name, )
        else:
            return u'function () { }'


class JsGlobalCode(JsExecutableCode):
    pass


class JsEvalCode(JsExecutableCode):
    def is_eval_code(self):
        return True


class JsFunction(JsExecutableCode):
    def __init__(self, name, js_code):
        JsExecutableCode.__init__(self, js_code)
        self._name_ = name

    def name(self):
        return self._name_

    def is_function_code(self):
        return True
