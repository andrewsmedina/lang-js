# encoding: utf-8
from pypy.rpython.lltypesystem import rffi
from pypy.rlib.rarithmetic import r_uint, intmask, ovfcheck_float_to_int
from pypy.rlib.rfloat import isnan, isinf, NAN, formatd
from js.execution import ThrowException, JsTypeError, RangeError, ReturnException

from pypy.rlib.jit import hint
from pypy.rlib import jit, debug
from js.utils import StackMixin

import string
# see ECMA 8.6.1 Property attributes
DE = 1 # DontEnum
DD = 2 # DontDelete
RO = 4 # ReadOnly
IT = 8 # Internal

class SeePage(NotImplementedError):
    pass

class Property(object):
    def __init__(self, name, value, flags = 0):
        self.name = name
        self.value = value
        self.flags = flags

    def __repr__(self):
        return "|%s : %s %d|"%(self.name, self.value, self.flags)

def internal_property(name, value):
    """return a internal property with the right attributes"""
    return Property(name, value, True, True, True, True)

class W_Root(object):

    def __init__(self):
        pass
    #def GetValue(self):
    #    return self

    def ToBoolean(self):
        raise NotImplementedError(self.__class__)

    def ToPrimitive(self, ctx, hint=""):
        return self

    def ToString(self, ctx):
        return ''

    def ToObject(self, ctx):
        # XXX should raise not implemented
        return self

    def ToNumber(self, ctx):
        return 0.0

    def ToInteger(self, ctx):
        return int(self.ToNumber(ctx))

    def ToInt32(self, ctx):
        return r_int32(int(self.ToNumber(ctx)))

    def ToUInt32(self, ctx):
        return r_uint32(0)

    def Get(self, ctx, P):
        raise NotImplementedError(self.__class__)

    def Put(self, ctx, P, V, flags = 0):
        raise NotImplementedError(self.__class__)

    def PutValue(self, w, ctx):
        pass

    def Call(self, ctx, args=[], this=None):
        raise NotImplementedError(self.__class__)

    def __str__(self):
        return self.ToString(ctx=None)

    def type(self):
        raise NotImplementedError(self.__class__)

    def GetPropertyName(self):
        raise NotImplementedError(self.__class__)

class W_Undefined(W_Root):
    def __str__(self):
        return "w_undefined"

    def ToInteger(self, ctx):
        return 0

    def ToNumber(self, ctx):
        return NAN

    def ToBoolean(self):
        return False

    def ToString(self, ctx):
        return "undefined"

    def type(self):
        return 'undefined'

class W_Null(W_Root):
    def __str__(self):
        return "null"

    def ToBoolean(self):
        return False

    def ToString(self, ctx):
        return "null"

    def type(self):
        return 'null'

w_Undefined = W_Undefined()
w_Null = W_Null()

class W_ContextObject(W_Root):
    def __init__(self, ctx):
        self.context = ctx

    def __repr__(self):
        return '<W_ContextObject (%s)>' % (repr(self.context),)

    def Get(self, ctx, name):
        try:
            return self.context.get_property_value(name)
        except KeyError:
            from js.jsobj import w_Undefined
            return w_Undefined

    def Put(self, ctx, P, V, flags = 0):
        self.context.put(P, V)

    def Delete(self, name):
        try:
            from jsobj import DD
            if self.context.get_property_flags(name) & DD:
                return False
            self.context.delete_identifier(name)
        except KeyError:
            pass
        return True

class W_PrimitiveObject(W_Root):
    def __init__(self, ctx=None, Prototype=None, Class='Object',
                 Value=w_Undefined, callfunc=None):
        self.propdict = {}
        self.Prototype = Prototype
        if Prototype is None:
            Prototype = w_Undefined
        self.propdict['prototype'] = Property('prototype', Prototype, flags = DE|DD)
        self.Class = Class
        self.callfunc = callfunc
        if callfunc is not None:
            self.ctx = ctx
        else:
            self.Scope = None
        self.Value = Value

    #@jit.unroll_safe
    def Call(self, ctx, args=[], this=None):
        if self.callfunc is None: # XXX Not sure if I should raise it here
            raise JsTypeError('not a function')
        from js.jsobj import W_Root
        assert isinstance(this, W_Root)

        from js.jsexecution_context import ActivationContext, ExecutionContext

        w_Arguments = W_Arguments(self, args)
        act = ActivationContext(self.ctx, this, w_Arguments)
        newctx = ExecutionContext(act)

        paramn = len(self.callfunc.params)
        for i in range(paramn):
            paramname = self.callfunc.params[i]
            try:
                value = args[i]
            except IndexError:
                value = w_Undefined
            newctx.declare_variable(paramname)
            newctx.assign(paramname, value)

        val = self.callfunc.run(ctx=newctx)
        return val

    def Construct(self, ctx, args=[]):
        obj = W_Object(Class='Object')
        prot = self.Get(ctx, 'prototype')
        if isinstance(prot, W_PrimitiveObject):
            obj.Prototype = prot
        else: # would love to test this
            #but I fail to find a case that falls into this
            obj.Prototype = ctx.get_global().Get(ctx, 'Object').Get(ctx, 'prototype')
        try: #this is a hack to be compatible to spidermonkey
            self.Call(ctx, args, this=obj)
            return obj
        except ReturnException, e:
            return e.value

    def Get(self, ctx, P):
        try:
            return self.propdict[P].value
        except KeyError:
            if self.Prototype is None:
                return w_Undefined
        return self.Prototype.Get(ctx, P) # go down the prototype chain

    def CanPut(self, P):
        if P in self.propdict:
            if self.propdict[P].flags & RO: return False
            return True
        if self.Prototype is None: return True
        return self.Prototype.CanPut(P)

    def Put(self, ctx, P, V, flags = 0):

        if not self.CanPut(P): return
        if P in self.propdict:
            prop = self.propdict[P]
            prop.value = V
            prop.flags |= flags
        else:
            self.propdict[P] = Property(P, V, flags = flags)

    def HasProperty(self, P):
        if P in self.propdict: return True
        if self.Prototype is None: return False
        return self.Prototype.HasProperty(P)

    def Delete(self, P):
        if P in self.propdict:
            if self.propdict[P].flags & DD:
                return False
            del self.propdict[P]
            return True
        return True

    def internal_def_value(self, ctx, tryone, trytwo):
        t1 = self.Get(ctx, tryone)
        if isinstance(t1, W_PrimitiveObject):
            val = t1.Call(ctx, this=self)
            if isinstance(val, W_Primitive):
                return val
        t2 = self.Get(ctx, trytwo)
        if isinstance(t2, W_PrimitiveObject):
            val = t2.Call(ctx, this=self)
            if isinstance(val, W_Primitive):
                return val
        raise JsTypeError

    def DefaultValue(self, ctx, hint=""):
        if hint == "String":
            return self.internal_def_value(ctx, "toString", "valueOf")
        else: # hint can only be empty, String or Number
            return self.internal_def_value(ctx, "valueOf", "toString")

    ToPrimitive = DefaultValue

    def ToBoolean(self):
        return True

    def ToString(self, ctx):
        try:
            res = self.ToPrimitive(ctx, 'String')
        except JsTypeError:
            return "[object %s]"%(self.Class,)
        return res.ToString(ctx)

    def __str__(self):
        return "<Object class: %s>" % self.Class

    def type(self):
        if self.callfunc is not None:
            return 'function'
        else:
            return 'object'


class W_Primitive(W_Root):
    """unifying parent for primitives"""
    def ToPrimitive(self, ctx, hint=""):
        return self

def str_builtin(ctx, args, this):
    return W_String(this.ToString(ctx))

class W_Object(W_PrimitiveObject):
    def __init__(self, ctx=None, Prototype=None, Class='Object',
                 Value=w_Undefined, callfunc=None):
        W_PrimitiveObject.__init__(self, ctx, Prototype,
                                   Class, Value, callfunc)

    def ToNumber(self, ctx):
        return self.Get(ctx, 'valueOf').Call(ctx, args=[], this=self).ToNumber(ctx)

class W_NewBuiltin(W_PrimitiveObject):
    length = -1
    def __init__(self, ctx, Prototype=None, Class='function',
                 Value=w_Undefined, callfunc=None):
        if Prototype is None:
            proto = ctx.get_global().Get(ctx, 'Function').Get(ctx, 'prototype')
            Prototype = proto

        W_PrimitiveObject.__init__(self, ctx, Prototype, Class, Value, callfunc)

        if self.length != -1:
            self.Put(ctx, 'length', W_IntNumber(self.length), flags = DE|DD|RO)


    def Call(self, ctx, args=[], this = None):
        raise NotImplementedError

    def type(self):
        return self.Class

class W_Builtin(W_PrimitiveObject):
    def __init__(self, builtin=None, ctx=None, Prototype=None, Class='function',
                 Value=w_Undefined, callfunc=None):
        W_PrimitiveObject.__init__(self, ctx, Prototype, Class, Value, callfunc)
        self.set_builtin_call(builtin)

    def set_builtin_call(self, callfuncbi):
        self.callfuncbi = callfuncbi

    def Call(self, ctx, args=[], this = None):
        return self.callfuncbi(ctx, args, this)

    def Construct(self, ctx, args=[]):
        return self.callfuncbi(ctx, args, None)

    def type(self):
        return self.Class

class W_ListObject(W_PrimitiveObject):
    def tolist(self):
        l = []
        for i in range(self.length):
            l.append(self.propdict[str(i)].value)
        return l

class W_Arguments(W_ListObject):
    def __init__(self, callee, args):
        W_PrimitiveObject.__init__(self, Class='Arguments')
        del self.propdict["prototype"]
        # XXX None can be dangerous here
        self.Put(None, 'callee', callee)
        self.Put(None, 'length', W_IntNumber(len(args)))
        for i in range(len(args)):
            self.Put(None, str(i), args[i])
        self.length = len(args)

class ActivationObject(W_PrimitiveObject):
    """The object used on function calls to hold arguments and this"""
    def __init__(self):
        W_PrimitiveObject.__init__(self, Class='Activation')
        del self.propdict["prototype"]

    def __repr__(self):
        return str(self.propdict)

class W_Array(W_ListObject):
    def __init__(self, ctx=None, Prototype=None, Class='Array',
                 Value=w_Undefined, callfunc=None):
        W_ListObject.__init__(self, ctx, Prototype, Class, Value, callfunc)
        self.Put(ctx, 'length', W_IntNumber(0), flags = DD)
        self.length = r_uint(0)

    def set_length(self, newlength):
        if newlength < self.length:
            i = newlength
            while i < self.length:
                key = str(i)
                if key in self.propdict:
                    del self.propdict[key]
                i += 1

        self.length = newlength
        self.propdict['length'].value = W_FloatNumber(newlength)

    def Put(self, ctx, P, V, flags = 0):
        if not self.CanPut(P): return
        if not P in self.propdict:
            self.propdict[P] = Property(P, V, flags = flags)
        else:
            if P != 'length':
                self.propdict[P].value = V
            else:
                length = V.ToUInt32(ctx)
                if length != V.ToNumber(ctx):
                    raise RangeError()

                self.set_length(length)
                return

        try:
            arrayindex = r_uint(to_array_index(P))
        except ValueError:
            return

        if (arrayindex < self.length) or (arrayindex != float(P)):
            return
        else:
            if (arrayindex + 1) == 0:
                raise RangeError()
            self.set_length(arrayindex+1)

class W_Boolean(W_Primitive):
    _immutable_fields_ = ['boolval']
    def __init__(self, boolval):
        self.boolval = bool(boolval)

    def ToObject(self, ctx):
        return create_object(ctx, 'Boolean', Value=self)

    def ToString(self, ctx=None):
        if self.boolval == True:
            return "true"
        return "false"

    def ToNumber(self, ctx):
        if self.boolval:
            return 1.0
        return 0.0

    def ToBoolean(self):
        return self.boolval

    def type(self):
        return 'boolean'

    def __repr__(self):
        return "<W_Bool "+str(self.boolval)+" >"

class W_String(W_Primitive):
    def __init__(self, strval):
        W_Primitive.__init__(self)
        self.strval = strval

    def __repr__(self):
        return 'W_String(%s)' % (self.strval,)

    def ToObject(self, ctx):
        o = create_object(ctx, 'String', Value=self)
        o.Put(ctx, 'length', W_IntNumber(len(self.strval)), flags = RO|DD|DE)
        return o

    def ToString(self, ctx=None):
        return self.strval

    def ToBoolean(self):
        if len(self.strval) == 0:
            return False
        else:
            return True

    def type(self):
        return 'string'

    def GetPropertyName(self):
        return self.ToString()

    def ToNumber(self, ctx):
        if not self.strval:
            return 0.0
        try:
            return float(self.strval)
        except ValueError:
            try:
                return float(int(self.strval, 16))
            except ValueError:
                try:
                    return float(int(self.strval, 8))
                except ValueError:
                    return NAN


class W_BaseNumber(W_Primitive):
    """ Base class for numbers, both known to be floats
    and those known to be integers
    """
    def ToObject(self, ctx):
        return create_object(ctx, 'Number', Value=self)

    def Get(self, ctx, P):
        return w_Undefined

    def type(self):
        return 'number'

class W_IntNumber(W_BaseNumber):
    _immutable_fields_ = ['intval']
    """ Number known to be an integer
    """
    def __init__(self, intval):
        W_BaseNumber.__init__(self)
        self.intval = intmask(intval)

    def ToString(self, ctx=None):
        # XXX incomplete, this doesn't follow the 9.8.1 recommendation
        return str(self.intval)

    def ToBoolean(self):
        return bool(self.intval)

    def ToNumber(self, ctx):
        # XXX
        return float(self.intval)

    def ToInt32(self, ctx):
        return r_int32(self.intval)

    def ToUInt32(self, ctx):
        return r_uint32(self.intval)

    def GetPropertyName(self):
        return self.ToString()

    def __repr__(self):
        return 'W_IntNumber(%s)' % (self.intval,)

def r_int32(n):
    return intmask(rffi.cast(rffi.INT, n))

def r_uint32(n):
    return intmask(rffi.cast(rffi.UINT, n))

class W_FloatNumber(W_BaseNumber):
    _immutable_fields_ = ['floatval']
    """ Number known to be a float
    """
    def __init__(self, floatval):
        W_BaseNumber.__init__(self)
        self.floatval = float(floatval)

    def ToString(self, ctx = None):
        # XXX incomplete, this doesn't follow the 9.8.1 recommendation
        if isnan(self.floatval):
            return 'NaN'
        if isinf(self.floatval):
            if self.floatval > 0:
                return 'Infinity'
            else:
                return '-Infinity'
        res = ''
        try:
            res = formatd(self.floatval, 'g', 10)
        except OverflowError:
            raise

        if len(res) > 3 and (res[-3] == '+' or res[-3] == '-') and res[-2] == '0':
            cut = len(res) - 2
            assert cut >= 0
            res = res[:cut] + res[-1]
        return res

    def ToBoolean(self):
        if isnan(self.floatval):
            return False
        return bool(self.floatval)

    def ToNumber(self, ctx):
        return self.floatval

    def ToInteger(self, ctx):
        if isnan(self.floatval):
            return 0

        if self.floatval == 0 or isinf(self.floatval):
            return self.floatval

        return intmask(int(self.floatval))

    def ToInt32(self, ctx):
        if isnan(self.floatval) or isinf(self.floatval):
            return 0
        return r_int32(int(self.floatval))

    def ToUInt32(self, ctx):
        if isnan(self.floatval) or isinf(self.floatval):
            return r_uint(0)
        return r_uint32(int(self.floatval))

    def __repr__(self):
        return 'W_FloatNumber(%s)' % (self.floatval,)

class W_List(W_Root):
    def __init__(self, list_w):
        self.list_w = list_w

    def ToString(self, ctx = None):
        raise SeePage(42)

    def ToBoolean(self):
        return bool(self.list_w)

    def get_args(self):
        return self.list_w

    def tolist(self):
        return self.list_w

    def __repr__(self):
        return 'W_List(%s)' % (self.list_w,)

class W_Iterator(W_Root):
    def __init__(self, elements_w):
        self.elements_w = elements_w

    def next(self):
        if self.elements_w:
            return self.elements_w.pop()

    def empty(self):
        return len(self.elements_w) == 0

def create_object(ctx, prototypename, callfunc=None, Value=w_Undefined):
    proto = ctx.get_global().Get(ctx, prototypename).Get(ctx, 'prototype')
    obj = W_Object(ctx, callfunc = callfunc,Prototype=proto,
                    Class = proto.Class, Value = Value)
    obj.Put(ctx, '__proto__', proto, DE|DD|RO)
    return obj

def isnull_or_undefined(obj):
    if obj is w_Null or obj is w_Undefined:
        return True
    return False

def to_array_index(s):
    '''Convert s to an integer if (and only if) s is a valid array index.
    ValueError is raised if conversion is not possible.
    '''
    length = len(s)

    if length == 0 or length > 10: # len(str(2 ** 32))
        raise ValueError

    # '0' is only valid if no characters follow it
    if s[0] == '0':
        if length == 1:
            return 0
        else:
            raise ValueError

    arrayindex = 0
    for i in range(length):
        if s[i] not in string.digits:
            raise ValueError
        arrayindex = (arrayindex * 10) + (ord(s[i]) - ord('0'))
        #XXX: check for overflow?
    return arrayindex

w_True = W_Boolean(True)
w_False = W_Boolean(False)

def newbool(val):
    if val:
        return w_True
    return w_False
