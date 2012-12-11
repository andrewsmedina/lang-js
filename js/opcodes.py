from js.jsobj import W_IntNumber, W_FloatNumber, W_String, \
    w_Undefined, newbool, w_Null, _w
from js.execution import JsTypeError
from js.baseop import plus, sub, compare, AbstractEC, StrictEC,\
    compare_e, increment, decrement, mult, division, uminus, mod
from pypy.rlib.rarithmetic import intmask

from js.jsobj import put_property


class Opcode(object):
    _stack_change = 1

    def __init__(self):
        pass

    def eval(self, ctx):
        """ Execute in context ctx
        """
        raise NotImplementedError

    def stack_change(self):
        return self._stack_change

    def __str__(self):
        return self.__class__.__name__


class BaseBinaryComparison(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        s4 = ctx.stack_pop()
        s2 = ctx.stack_pop()
        ctx.stack_append(self.decision(ctx, s2, s4))

    def decision(self, ctx, op1, op2):
        raise NotImplementedError


class BaseBinaryBitwiseOp(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        s5 = ctx.stack_pop().ToInt32()
        s6 = ctx.stack_pop().ToInt32()
        ctx.stack_append(self.operation(ctx, s5, s6))

    def operation(self, ctx, op1, op2):
        raise NotImplementedError


class BaseBinaryOperation(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        right = ctx.stack_pop()
        left = ctx.stack_pop()
        ctx.stack_append(self.operation(ctx, left, right))


class BaseUnaryOperation(Opcode):
    _stack_change = 0


class Undefined(Opcode):
    def eval(self, ctx):
        ctx.stack_append(w_Undefined)


class LOAD_INTCONSTANT(Opcode):
    _immutable_fields_ = ['w_intvalue']

    def __init__(self, value):
        self.w_intvalue = W_IntNumber(int(value))

    def eval(self, ctx):
        ctx.stack_append(self.w_intvalue)

    def __str__(self):
        return 'LOAD_INTCONSTANT %s' % (self.w_intvalue.ToInteger(),)


class LOAD_BOOLCONSTANT(Opcode):
    def __init__(self, value):
        self.boolval = value

    def eval(self, ctx):
        ctx.stack_append(newbool(self.boolval))

    def __str__(self):
        if self.boolval:
            return 'LOAD_BOOLCONSTANT true'
        return 'LOAD_BOOLCONSTANT false'


class LOAD_FLOATCONSTANT(Opcode):
    def __init__(self, value):
        self.w_floatvalue = W_FloatNumber(float(value))

    def eval(self, ctx):
        ctx.stack_append(self.w_floatvalue)

    def __str__(self):
        return 'LOAD_FLOATCONSTANT %s' % (self.w_floatvalue.ToNumber(),)


class LOAD_STRINGCONSTANT(Opcode):
    _immutable_fields_ = ['w_stringvalue']

    def __init__(self, value):
        #assert isinstance(value, unicode)
        self.strval = value

    def eval(self, ctx):
        strval = self.strval
        #assert isinstance(strval, unicode)
        w_string = W_String(strval)
        ctx.stack_append(w_string)

    def __str__(self):
        return u'LOAD_STRINGCONSTANT "%s"' % (self.strval)


class LOAD_UNDEFINED(Opcode):
    def eval(self, ctx):
        ctx.stack_append(w_Undefined)


class LOAD_NULL(Opcode):
    def eval(self, ctx):
        ctx.stack_append(w_Null)


class LOAD_VARIABLE(Opcode):
    _immutable_fields_ = ['identifier', 'index']

    def __init__(self, index, identifier):
        assert index is not None
        self.index = index
        self.identifier = identifier

    # 11.1.2
    def eval(self, ctx):
        # TODO put ref onto stack
        value = ref.get_value()
        ref = ctx.get_ref(self.identifier, self.index)
        ctx.stack_append(value)

    def __str__(self):
        return 'LOAD_VARIABLE "%s"' % (self.identifier)


class LOAD_THIS(Opcode):
    # 11.1.1
    def eval(self, ctx):
        this = ctx.this_binding()
        ctx.stack_append(this)


class LOAD_ARRAY(Opcode):
    def __init__(self, counter):
        self.counter = counter

    def eval(self, ctx):
        from js.object_space import object_space
        array = object_space.new_array()

        list_w = ctx.stack_pop_n(self.counter)  # [:] # pop_n returns a non-resizable list
        for index, el in enumerate(list_w):
            array.put(unicode(str(index)), el)
        ctx.stack_append(array)

    def stack_change(self):
        return -1 * self.counter + 1

    def __str__(self):
        return 'LOAD_ARRAY %d' % (self.counter,)


class LOAD_LIST(Opcode):
    #_immutable_fields_ = ['counter']
    def __init__(self, counter):
        self.counter = counter

    def eval(self, ctx):
        from js.jsobj import W_List
        list_w = ctx.stack_pop_n(self.counter)  # [:] # pop_n returns a non-resizable list
        ctx.stack_append(W_List(list_w))

    def stack_change(self):
        return -1 * self.counter + 1

    def __str__(self):
        return u'LOAD_LIST %d' % (self.counter,)


class LOAD_FUNCTION(Opcode):
    def __init__(self, funcobj):
        self.funcobj = funcobj

    # 13.2 Creating Function Objects
    def eval(self, ctx):
        from js.object_space import object_space

        func = self.funcobj
        scope = ctx.lexical_environment()
        params = func.params()
        strict = func.strict
        w_func = object_space.new_func(func, formal_parameter_list=params, scope=scope, strict=strict)

        ctx.stack_append(w_func)

    #def __repr__(self):
        #return 'LOAD_FUNCTION' # XXX


class LOAD_OBJECT(Opcode):
    _immutable_fields_ = ["counter"]

    def __init__(self, counter):
        self.counter = counter

    def eval(self, ctx):
        from js.object_space import object_space
        w_obj = object_space.new_obj()
        for _ in range(self.counter):
            name = ctx.stack_pop().to_string()
            w_elem = ctx.stack_pop()
            put_property(w_obj, name, w_elem, writable=True, configurable=True, enumerable=True)
        ctx.stack_append(w_obj)

    #def __repr__(self):
        #return 'LOAD_OBJECT %d' % (self.counter,)


class LOAD_MEMBER(Opcode):
    _stack_change = -1

    def eval(self, ctx):
        w_obj = ctx.stack_pop().ToObject()
        name = ctx.stack_pop().to_string()
        value = w_obj.get(name)
        ctx.stack_append(value)

    def __str__(self):
        return 'LOAD_MEMBER'


class COMMA(BaseUnaryOperation):
    def eval(self, ctx):
        one = ctx.stack_pop()
        ctx.stack_pop()
        ctx.stack_append(one)
        # XXX


class SUB(BaseBinaryOperation):
    def operation(self, ctx, left, right):
        return sub(ctx, left, right)


class IN(BaseBinaryOperation):
    def operation(self, ctx, left, right):
        from js.jsobj import W_BasicObject
        if not isinstance(right, W_BasicObject):
            raise JsTypeError(u"TypeError: fffuuu!")  # + repr(right)
        name = left.to_string()
        has_name = right.has_property(name)
        return newbool(has_name)


# 11.4.3
def type_of(var):
    var_type = var.type()
    if var_type == 'null':
        return u'object'
    return unicode(var_type)


class TYPEOF(BaseUnaryOperation):
    def eval(self, ctx):
        var = ctx.stack_pop()
        var_type = type_of(var)
        ctx.stack_append(_w(var_type))


class TYPEOF_VARIABLE(Opcode):
    def __init__(self, index, name):
        self.index = index
        self.name = name

    def eval(self, ctx):
        ref = ctx.get_ref(self.name)
        if ref.is_unresolvable_reference():
            var_type = u'undefined'
        else:
            var = ref.get_value()
            var_type = type_of(var)

        w_string = W_String(var_type)
        ctx.stack_append(w_string)

    def __str__(self):
        return 'TYPEOF_VARIABLE %s' % (self.name)


class ADD(BaseBinaryOperation):
    def operation(self, ctx, left, right):
        return plus(ctx, left, right)


class BITAND(BaseBinaryBitwiseOp):
    def operation(self, ctx, op1, op2):
        return W_IntNumber(op1 & op2)


class BITXOR(BaseBinaryBitwiseOp):
    def operation(self, ctx, op1, op2):
        return W_IntNumber(op1 ^ op2)


class BITOR(BaseBinaryBitwiseOp):
    def operation(self, ctx, op1, op2):
        return W_IntNumber(op1 | op2)


class BITNOT(BaseUnaryOperation):
    def eval(self, ctx):
        op = ctx.stack_pop().ToInt32()
        ctx.stack_append(W_IntNumber(~op))


class URSH(BaseBinaryBitwiseOp):
    def eval(self, ctx):
        rval = ctx.stack_pop()
        lval = ctx.stack_pop()

        rnum = rval.ToUInt32()
        lnum = lval.ToUInt32()

        from pypy.rlib.rarithmetic import ovfcheck_float_to_int

        shift_count = rnum & 0x1F
        res = lnum >> shift_count

        try:
            ovfcheck_float_to_int(res)
            w_res = _w(res)
        except OverflowError:
            w_res = _w(float(res))

        ctx.stack_append(w_res)


class RSH(BaseBinaryBitwiseOp):
    def eval(self, ctx):
        rval = ctx.stack_pop()
        lval = ctx.stack_pop()

        rnum = rval.ToUInt32()
        lnum = lval.ToInt32()
        shift_count = rnum & 0x1F
        res = lnum >> shift_count

        ctx.stack_append(_w(res))


class LSH(BaseBinaryBitwiseOp):
    def eval(self, ctx):
        from js.jsobj import int32
        rval = ctx.stack_pop()
        lval = ctx.stack_pop()

        lnum = lval.ToInt32()
        rnum = rval.ToUInt32()

        shift_count = intmask(rnum & 0x1F)
        res = int32(lnum << shift_count)

        ctx.stack_append(_w(res))


class MUL(BaseBinaryOperation):
    def operation(self, ctx, op1, op2):
        return mult(ctx, op1, op2)


class DIV(BaseBinaryOperation):
    def operation(self, ctx, op1, op2):
        return division(ctx, op1, op2)


class MOD(BaseBinaryOperation):
    def operation(self, ctx, op1, op2):
        return mod(ctx, op1, op2)


class UPLUS(BaseUnaryOperation):
    def eval(self, ctx):
        expr = ctx.stack_pop()
        num = expr.ToNumber()
        res = _w(num)
        ctx.stack_append(res)


class UMINUS(BaseUnaryOperation):
    def eval(self, ctx):
        ctx.stack_append(uminus(ctx.stack_pop(), ctx))


class NOT(BaseUnaryOperation):
    def eval(self, ctx):
        val = ctx.stack_pop()
        boolval = val.to_boolean()
        inv_boolval = not boolval
        ctx.stack_append(_w(inv_boolval))


class INCR(BaseUnaryOperation):
    def eval(self, ctx):
        value = ctx.stack_pop()
        num = _w(value.ToNumber())
        newvalue = increment(ctx, num)
        ctx.stack_append(newvalue)


class DECR(BaseUnaryOperation):
    def eval(self, ctx):
        value = ctx.stack_pop()
        num = _w(value.ToNumber())
        newvalue = decrement(ctx, num)
        ctx.stack_append(newvalue)


class GT(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(compare(ctx, op1, op2))


class GE(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(compare_e(ctx, op1, op2))


class LT(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(compare(ctx, op2, op1))


class LE(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(compare_e(ctx, op2, op1))


class EQ(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(AbstractEC(ctx, op1, op2))


class NE(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(not AbstractEC(ctx, op1, op2))


class IS(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(StrictEC(op1, op2))


class ISNOT(BaseBinaryComparison):
    def decision(self, ctx, op1, op2):
        return newbool(not StrictEC(op1, op2))


class STORE_MEMBER(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        left = ctx.stack_pop()
        member = ctx.stack_pop()
        name = member.to_string()
        #assert isinstance(name, unicode)

        value = ctx.stack_pop()

        l_obj = left.ToObject()
        l_obj.put(name, value)

        ctx.stack_append(value)


class STORE(Opcode):
    _immutable_fields_ = ['identifier', 'index']
    _stack_change = 0

    def __init__(self, index, identifier):
        assert index is not None
        self.index = index
        self.identifier = identifier

    def eval(self, ctx):
        value = ctx.stack_top()
        ref.put_value(value)
        ref = ctx.get_ref(self.identifier, self.index)

    def __str__(self):
        return 'STORE "%s"' % (self.identifier)


class LABEL(Opcode):
    _stack_change = 0

    def __init__(self, num):
        self.num = num

    def __str__(self):
        return 'LABEL %d' % (self.num)

    #def __repr__(self):
        #return 'LABEL %d' % (self.num,)


class BaseJump(Opcode):
    _immutable_fields_ = ['where']
    _stack_change = 0

    def __init__(self, where):
        self.where = where
        self.decision = False

    def do_jump(self, ctx, pos):
        return 0

    #def __repr__(self):
        #return '%s %d' % (self.__class__.__name__, self.where)


class JUMP(BaseJump):
    def eval(self, ctx):
        pass

    def do_jump(self, ctx, pos):
        return self.where

    def __str__(self):
        return 'JUMP %d' % (self.where)


class BaseIfJump(BaseJump):
    def eval(self, ctx):
        value = ctx.stack_pop()
        self.decision = value.to_boolean()


class BaseIfNopopJump(BaseJump):
    def eval(self, ctx):
        value = ctx.stack_top()
        self.decision = value.to_boolean()


class JUMP_IF_FALSE(BaseIfJump):
    def do_jump(self, ctx, pos):
        if self.decision:
            return pos + 1
        return self.where

    def __str__(self):
        return 'JUMP_IF_FALSE %d' % (self.where)


class JUMP_IF_FALSE_NOPOP(BaseIfNopopJump):
    def do_jump(self, ctx, pos):
        if self.decision:
            ctx.stack_pop()
            return pos + 1
        return self.where

    def __str__(self):
        return 'JUMP_IF_FALSE_NOPOP %d' % (self.where)


class JUMP_IF_TRUE(BaseIfJump):
    def do_jump(self, ctx, pos):
        if self.decision:
            return self.where
        return pos + 1

    def __str__(self):
        return 'JUMP_IF_TRUE %d' % (self.where)


class JUMP_IF_TRUE_NOPOP(BaseIfNopopJump):
    def do_jump(self, ctx, pos):
        if self.decision:
            return self.where
        ctx.stack_pop()
        return pos + 1

    def __str__(self):
        return 'JUMP_IF_TRUE_NOPOP %d' % (self.where)


class DECLARE_FUNCTION(Opcode):
    _stack_change = 0

    def __init__(self, funcobj):
        self.funcobj = funcobj

    def eval(self, ctx):
        pass
        #from js.jsobj import DONT_ENUM, READ_ONLY
        ## 13.2 Creating Function Objects
        ## TODO move this to W__Function.__init__ ?

        #func = W__Function(ctx, self.funcobj)

        #func.Put('length', W_IntNumber(len(self.funcobj.params())), flags = DONT_ENUM | READ_ONLY)

        #proto = W__Object()
        #proto.Put('constructor', func, flags = DONT_ENUM)

        #func.Put('prototype', proto, flags = DONT_ENUM)

        #ctx.stack_append(funcobj)

        #if self.funcobj.name is not None:
            #ctx.set_value(self.funcobj.name, func)

    def __str__(self):
        funcobj = self.funcobj
        if funcobj.name is None:
            name = ""
        else:
            name = funcobj.name + " "
        return 'DECLARE_FUNCTION %s%r' % (name, funcobj.params)

    ##def __repr__(self):
    ##    funcobj = self.funcobj
    ##    if funcobj.name is None:
    ##        name = ""
    ##    else:
    ##        name = funcobj.name + " "
    ##    codestr = '\n'.join(['  %r' % (op,) for op in funcobj.opcodes])
    ##    ##return 'DECLARE_FUNCTION %s%r [\n%s\n]' % (name, funcobj.params, codestr)
    ##    return 'DECLARE_FUNCTION %s%r' % (name, funcobj.params)


class DECLARE_VAR(Opcode):
    _stack_change = 0

    def __init__(self, name):
        self.name = name

    def eval(self, ctx):
        pass
        #ctx.declare_variable(self.name)

    #def __repr__(self):
        #return 'DECLARE_VAR "%s"' % (self.name,)


class RETURN(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        from js.completion import ReturnCompletion
        value = ctx.stack_top()
        return ReturnCompletion(value)


class POP(Opcode):
    _stack_change = -1

    def eval(self, ctx):
        ctx.stack_pop()


def common_call(ctx, r1, args, this, name):
    # TODO
    from js.jsobj import W_BasicFunction
    if not (isinstance(r1, W_BasicFunction)):
        #err = (u"%s is not a callable (%s)"%(r1.to_string(), name.to_string()))
        err = u"is not a callable (%s)"
        raise JsTypeError(err)
    argv = args.to_list()
    res = r1.Call(args=argv, this=this, calling_context=ctx)
    return res


class CALL(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        r1 = ctx.stack_pop()
        args = ctx.stack_pop()
        this = ctx.implicit_this_binding()
        res = common_call(ctx, r1, args, this, r1)
        ctx.stack_append(res)


class CALL_METHOD(Opcode):
    _stack_change = -2

    def eval(self, ctx):
        method = ctx.stack_pop()
        what = ctx.stack_pop().ToObject()
        args = ctx.stack_pop()
        name = method.to_string()
        r1 = what.get(name)
        res = common_call(ctx, r1, args, what, method)
        ctx.stack_append(res)


class DUP(Opcode):
    def eval(self, ctx):
        ctx.stack_append(ctx.stack_top())


class THROW(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        val = ctx.stack_pop()
        from js.execution import JsThrowException
        raise JsThrowException(val)


class TRYCATCHBLOCK(Opcode):
    _stack_change = 0

    def __init__(self, tryfunc, catchparam, catchfunc, finallyfunc):
        self.tryexec = tryfunc
        self.catchexec = catchfunc
        self.catchparam = catchparam
        self.finallyexec = finallyfunc

    def eval(self, ctx):
        from js.completion import is_return_completion, is_completion, NormalCompletion
        from js.execution import JsException

        tryexec = self.tryexec
        catchexec = self.catchexec
        finallyexec = self.finallyexec
        catchparam = self.catchparam

        try:
            b = tryexec.run(ctx)
            assert is_completion(b)
        except JsException, e:
            if catchexec is not None:
                from js.execution_context import CatchExecutionContext
                msg = e.msg()
                catch_ctx = CatchExecutionContext(catchexec, catchparam, msg, ctx)
                res = catchexec.run(catch_ctx)
                assert is_completion(res)
                c = res
            else:
                c = NormalCompletion()
        else:
            assert is_completion(b)
            c = b

        if finallyexec is not None:
            f = finallyexec.run(ctx)
            if not is_return_completion(f):
                f = c
        else:
            f = c

        assert is_completion(f)

        if is_return_completion(f):
            return f
        else:
            ctx.stack_append(f.value)


def commonnew(ctx, obj, args):
    from js.jsobj import W_BasicFunction

    if not isinstance(obj, W_BasicFunction):
        raise JsTypeError(u'not a constructor')
    res = obj.Construct(args=args)
    return res


class NEW(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        from js.jsobj import W_List

        y = ctx.stack_pop()
        x = ctx.stack_pop()
        assert isinstance(y, W_List)
        args = y.to_list()
        res = commonnew(ctx, x, args)
        ctx.stack_append(res)


class NEW_NO_ARGS(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        x = ctx.stack_pop()
        res = commonnew(ctx, x, [])
        ctx.stack_append(res)

# ------------ iterator support ----------------

from pypy.rlib.listsort import make_timsort_class
TimSort = make_timsort_class()


class LOAD_ITERATOR(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        exper_value = ctx.stack_pop()
        obj = exper_value.ToObject()
        props = []

        from js.jsobj import W_BasicObject
        assert isinstance(obj, W_BasicObject)

        properties = obj.named_properties()
        TimSort(properties).sort()

        for key in properties:
            prop = obj.get_property(key)
            if prop.enumerable is True:
                props.append(_w(key))

        props.reverse()
        from js.jsobj import W_Iterator
        iterator = W_Iterator(props)

        ctx.stack_append(iterator)


class JUMP_IF_ITERATOR_EMPTY(BaseJump):
    def eval(self, ctx):
        pass

    def do_jump(self, ctx, pos):
        from js.jsobj import W_Iterator
        last_block_value = ctx.stack_pop()
        iterator = ctx.stack_top()
        assert isinstance(iterator, W_Iterator)
        if iterator.empty():
            # discard the iterator
            ctx.stack_pop()
            # put the last block value on the stack
            ctx.stack_append(last_block_value)
            return self.where
        return pos + 1

    def __str__(self):
        return 'JUMP_IF_ITERATOR_EMPTY %d' % (self.where)


class NEXT_ITERATOR(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        from js.jsobj import W_Iterator

        iterator = ctx.stack_top()
        assert isinstance(iterator, W_Iterator)
        next_el = iterator.next()
        ctx.stack_append(next_el)

        #ref = ctx.get_ref(self.name)
        #ref.put_value(next_el)

# ---------------- with support ---------------------


class WITH(Opcode):
    def __init__(self, body):
        self.body = body

    def eval(self, ctx):
        from js.completion import is_return_completion
        from execution_context import WithExecutionContext
        # 12.10
        expr = ctx.stack_pop()
        expr_obj = expr.ToObject()

        with_ctx = WithExecutionContext(self.body, expr_obj, ctx)

        c = self.body.run(with_ctx)
        if is_return_completion(c):
            return c
        else:
            ctx.stack_append(c.value)

# ------------------ delete -------------------------


class DELETE(Opcode):
    def __init__(self, name, index):
        self.name = name
        self.index = index

    def eval(self, ctx):
        from js.lexical_environment import Reference
        from js.execution import JsSyntaxError

        # 11.4.1
        ref = ctx.get_ref(self.name, self.index)
        if not isinstance(ref, Reference):
            res = True
        if ref.is_unresolvable_reference():
            if ref.is_strict_reference():
                raise JsSyntaxError()
            res = True
        if ref.is_property_reference():
            obj = ref.get_base().ToObject()
            res = obj.delete(ref.get_referenced_name(), ref.is_strict_reference())
        else:
            if ref.is_strict_reference():
                raise JsSyntaxError()
            bindings = ref.base_env
            res = bindings.delete_binding(ref.get_referenced_name())

        if res is True:
            ctx.forget_ref(self.name, self.index)
        ctx.stack_append(_w(res))


class DELETE_MEMBER(Opcode):
    _stack_change = 0

    def eval(self, ctx):
        what = ctx.stack_pop().to_string()
        obj = ctx.stack_pop().ToObject()
        res = obj.delete(what, False)
        ctx.stack_append(_w(res))


class LOAD_LOCAL(Opcode):
    _immutable_fields_ = ['local']

    def __init__(self, local):
        self.local = local

    def eval(self, ctx):
        ctx.stack_append(ctx.get_local_value(self.local))

    #def __repr__(self):
        #return 'LOAD_LOCAL %d' % (self.local,)


class STORE_LOCAL(Opcode):
    _stack_change = 0
    _immutable_fields_ = ['local']

    def __init__(self, local):
        self.local = local

    def eval(self, ctx):
        value = ctx.stack_top()
        ctx.assign_local(self.local, value)

    #def __repr__(self):
        #return 'STORE_LOCAL %d' % (self.local,)


class INSTANCEOF(Opcode):
    def eval(self, ctx):
        rval = ctx.stack_pop()
        lval = ctx.stack_pop()
        from js.jsobj import W_BasicObject
        if not isinstance(rval, W_BasicObject):
            raise JsTypeError(u'TypeError')
        res = rval.has_instance(lval)
        ctx.stack_append(_w(res))

# different opcode mappings, to make annotator happy

OpcodeMap = {}

for name, value in locals().items():
    if name.upper() == name and type(value) == type(Opcode) and issubclass(value, Opcode):
        OpcodeMap[name] = value


class Opcodes:
    pass

opcodes = Opcodes()
for name, value in OpcodeMap.items():
    setattr(opcodes, name, value)
