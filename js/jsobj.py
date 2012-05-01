# encoding: utf-8
from pypy.rpython.lltypesystem import rffi
from pypy.rlib.rarithmetic import r_uint, intmask, ovfcheck_float_to_int
from pypy.rlib.rfloat import isnan, isinf, NAN, formatd
from js.execution import ThrowException, JsTypeError, RangeError, ReturnException

from pypy.rlib.jit import hint
from pypy.rlib import jit, debug
from js.utils import StackMixin
from js.object_map import root_map

import string
# see ECMA 8.6.1 Property attributes
DONT_ENUM = DE = 1 # DontEnum
DONT_DELETE = DD = 2 # DontDelete
READ_ONLY = RO = 4 # ReadOnly
INTERNAL = IT = 8 # Internal

class W_Root(object):
    #_settled_ = True
    #_attrs_ = []
    _type_ = ''

    def __str__(self):
        return self.ToString()

    #def type(self):
        #return self._type_

    #def ToBoolean(self):
        #return False

    #def ToPrimitive(self, hint = None):
        #return self

    #def ToString(self):
        #return ''

    #def ToObject(self):
        #raise JsTypeError

    #def ToNumber(self):
        #return 0.0

    #def ToInteger(self):
        #return int(self.ToNumber())


class W_Primitive(W_Root):
    pass

class W_Undefined(W_Primitive):
    _type_ = 'undefined'
    def ToInteger(self):
        return 0

    def ToNumber(self):
        return NAN

    def ToString(self):
        return self._type_

class W_Null(W_Primitive):
    _type_ = 'null'

    def ToBoolean(self):
        return False

    def ToString(self):
        return self._type_

w_Undefined = W_Undefined()
w_Null = W_Null()

# 8.6.1
class Property(object):
    value = w_Undefined
    getter = w_Undefined
    setter = w_Undefined
    writable = False
    enumerable = False
    configurable = False

    def __init__(self, value = None, writable = None, getter = None, setter = None, enumerable = None, configurable = None):
        if value is not None:
            self.value = value
        if writable is not None:
            self.writable = writable
        if getter is not None:
            self.get = getter
        if setter is not None:
            self.setter = setter
        if writable is not None:
            self.writable = writable
        if configurable is not None:
            self.configurable = configurable

    def is_data_property(self):
        return False

    def is_accessor_property(self):
        return False

    def update_with(self, other):
        if other.value is not None:
            self.value = other.value
        if other.writable is not None:
            self.writable = other.writable
        if other.getter is not None:
            self.getter = other.getter
        if other.setter is not None:
            self.setter = other.setter
        if other.writable is not None:
            self.writable = other.writable
        if other.configurable is not None:
            self.configurable = other.configurable

class DataProperty(Property):
    def __init__(self, value = None, writable = None, enumerable = None, configurable = None):
        Property.__init__(self, value = value, writable = writable, enumerable = enumerable, configurable = configurable)

    def is_data_property(self):
        return True

class AccessorProperty(Property):
    def __init__(self, getter = None, setter = None, enumerable = None, configurable = None):
        Property.__init__(self, getter = None, setter = None, enumerable = enumerable, configurable = configurable)

    def is_accessor_property(self):
        return True

def is_data_descriptor(desc):
    if desc is w_Undefined:
        return False
    return desc.is_data_descriptor()

def is_accessor_descriptor(desc):
    if desc is w_Undefined:
        return False
    return desc.is_accessor_descriptor()

def is_generic_descriptor(desc):
    if desc is w_Undefined:
        return False
    return desc.is_generic_descriptor()

# 8.10
class PropertyDescriptor(object):
    value = None
    writable = None
    getter = None
    setter = None
    configurable = None
    enumerable = None

    def __init__(self, value = None, writable = None, getter = None, setter = None, configurable = None, enumerable = None):
        self.value = value
        self.writable = writable
        self.getter = getter
        self.setter = setter
        self.configurable = configurable
        self.enumerable = enumerable

    def is_accessor_descriptor(self):
        return self.getter is not None and self.setter is not None

    def is_data_descriptor(self):
        return self.value is not None and self.writable is not None

    def is_generic_descriptor(self):
        return self.is_accessor_descriptor() is False and self.is_data_descriptor() is False

    def is_empty(self):
        return self.getter is None\
            and self.setter is None\
            and self.value is None\
            and self.writable is None\
            and self.enumerable is None\
            and self.configurable is None

    def __eq__(self, other):
        assert isinstance(other, PropertyDescriptor)

        if self.setter is not None and self.setter != other.setter:
            return False

        if self.getter is not None and self.getter != other.getter:
            return False

        if self.writable is not None and self.writable != other.writable:
            return False

        if self.value is not None and self.value != other.value:
            return False

        if self.configurable is not None and self.configurable != other.configurable:
            return False

        if self.enumerable is not None and self.enumerable != other.enumerable:
            return False

    def update_with(self, other):
        assert isinstance(other, PropertyDescriptor)

        if other.enumerable is not None:
            self.enumerable = other.enumerable

        if other.configurable is not None:
            self.configurable = other.configurable

        if other.value is not None:
            self.value = other.value

        if other.writable is not None:
            self.writable = other.writable

        if other.getter is not None:
            self.getter = other.getter

        if other.setter is not None:
            self.setter = other.setter

class PropertyIdenfidier(object):
    def __init__(self, name, descriptor):
        self.name = name
        self.descriptor = descriptor

class W_BasicObject(W_Root):
    #_immutable_fields_ = ['_class_', '_prototype_', '_primitive_value_']
    _type_ = 'object'
    _class_ = 'Object'
    _prototype_ = w_Undefined
    _extensible_ = True

    def __init__(self):
        W_Root.__init__(self)
        self._properties_ = {}

    def __repr__(self):
        return "%s: %s" % (object.__repr__(self), self.klass())


    ##########
    # 8.6.2 Object Internal Properties and Methods
    def prototype(self):
        return self._prototype_

    def klass(self):
        return self._class_

    def extensible(self):
        return self._extensible_

    # 8.12.3
    def get(self, p):
        desc = self.get_property(p)

        if desc is w_Undefined:
            return w_Undefined

        if is_data_descriptor(desc):
            return desc.value

        getter = desc.getter
        if getter is w_Undefined:
            return w_Undefined

        # return getter.call(this = self)
        raise NotImplementedError(self.__class__)

    # 8.12.1
    def get_own_property(self, p):
        if p not in self._properties_:
            return w_Undefined

        d = PropertyDescriptor()
        x = self._properties_[p]

        if x.is_data_property():
            d.value = x.value
            d.writable = x.writable
        elif x.is_accessor_property:
            d.setter = x.setter
            d.getter = x.getter

        d.enumerable = x.enumerable
        d.configurable = x.configurable
        return d

    # 8.12.2
    def get_property(self, p):
        prop = self.get_own_property(p)
        if prop is not w_Undefined:
            return prop
        proto = self.prototype()

        if proto is w_Undefined:
            return w_Undefined

        return proto.get_property(p)

    # 8.12.5
    def put(self, p, v, throw = False):
        if self.can_put(p) is False:
            if throw is True:
                raise JsTypeError(self.__class__)

        own_desc = self.get_own_property(p)
        if is_data_descriptor(own_desc):
            value_desc = PropertyDescriptor(value = v)
            self.define_own_property(p, value_desc, throw)
            return

        desc = self.get_property(p)
        if is_accessor_descriptor(desc):
            setter = desc.setter
            assert setter is not None
            # setter.call(this = self, v)
            raise NotImplementedError(self.__class__)
        else:
            new_desc = PropertyDescriptor(value = v, writable = True, configurable = True, enumerable = True)
            self.define_own_property(p, new_desc, throw)

    # 8.12.4
    def can_put(self, p):
        desc = self.get_own_property(p)
        if desc is not w_Undefined:
            if is_accessor_descriptor(desc):
                if desc.setter is w_Undefined:
                    return False
                else:
                    return True
            return desc.writable

        proto = self.prototype()

        if proto is w_Null or proto is w_Undefined:
            return self.extensible()

        inherited = proto.GetProperty(p)
        if inherited is w_Undefined:
            return self.extensible()

        if is_accessor_descriptor(inherited):
            if inherited.setter is w_Undefined:
                return False
            else:
                return True
        else:
            if self.extensible() is False:
                return False
            else:
                return inherited.writable

    # 8.12.6
    def has_property(self, p):
        desc = self.get_property(p)
        if desc is w_Undefined:
            return False
        return True

    # 8.12.7
    def delete(self, p, throw):
        desc = self.get_own_property(p)
        if desc is w_Undefined:
            return True
        if desc.configurable:
            del self._properties_[p]
            return True

        if throw is True:
            raise JsTypeError(self.__class__)

    # 8.12.8
    def default_value(self, hint = 'Number'):
        if hint == 'String':
            res = self._default_value_string_()
            if res is None:
                res = self._default_value_number_()
        else:
            res = self._default_value_number_()
            if res is None:
                res = self._default_value_string_()

        if res is not None:
            return res

        raise JsTypeError(self.__class__)

    def _default_value_string_(self):
        to_string = self.get('toString')
        if to_string.is_callable():
            _str = to_string.call(this = self)
            if isinstance(_str, W_Primitive):
                return _str

    def _default_value_number_(self):
        value_of = self.get('valueOf')
        if value_of.is_callable():
            val = to_string.call(this = self)
            if isinstance(val, W_Primitive):
                return val

    # 8.12.9
    def define_own_property(self, p, desc, throw = False):
        def reject():
            if throw:
                raise JsTypeError(self.__class__)
            else:
                return False

        current = self.get_own_property(p)
        extensible = self.extensible()
        # 3.
        if current is w_Undefined and extensible is False:
            return reject()
        # 4.
        if current is w_Undefined and extensible is True:
            # 4.a
            if is_generic_descriptor(desc) or is_data_descriptor(desc):
                new_prop = DataProperty(\
                    value = desc.value,\
                    writable = desc.writable,\
                    enumerable = desc.enumerable,\
                    configurable = desc.configurable\
                )
                self._properties_[p] = new_prop
            # 4.b
            else:
                assert is_accessor_descriptor(desc) is True
                new_prop = AccessorProperty(\
                    getter = desc.getter,\
                    setter = desc.setter,\
                    enumerable = desc.enumerable,
                    configurable = desc.configurable\
                )
                self._properties_[p] = new_prop
            # 4.c
            return True

        # 5.
        if desc.is_empty():
            return True

        # 6.
        if desc == current:
            return True

        # 7.
        if current.configurable is False:
            if desc.configurable is True:
                return reject()
            if desc.enumerable is not None and current.enumerable != desc.enumerable:
                return reject()

        # 8.
        if is_generic_descriptor(desc):
            pass
        # 9.
        elif is_data_descriptor(current) != is_data_descriptor(desc):
            # 9.a
            if current.configurable is False:
                return reject()
            # 9.b
            if is_data_descriptor(current):
                raise NotImplementedError(self.__class__)
            # 9.c
            else:
                raise NotImplementedError(self.__class__)
        # 10
        elif is_data_descriptor(current) and is_data_descriptor(current):
            # 10.a
            if current.configurable is False:
                # 10.a.i
                if current.writable is False and desc.writable is True:
                    return reject()
                # 10.a.ii
                if current.writable is False:
                    if desc.value is not None and desc.value != current.value:
                        return reject()
            # 10.b
            else:
                pass
        # 11
        elif is_accessor_descriptor(current) and is_accessor_descriptor(desc):
            # 11.a
            if current.configurable is False:
                # 11.a.i
                if desc.setter is not None and desc.setter != current.setter:
                    return reject()
                # 11.a.ii
                if desc.getter is not None and desc.getter != current.getter:
                    return reject()
        # 12
        prop = self._properties_[p]
        prop.update_with(desc)

        # 13
        return True

    ##########
    def ToBoolean(self):
        return True

    def ToNumber(self):
        return self.ToPrimitive('Number').ToNumber()

    def ToString(self):
        return self.ToPrimitive('String').ToString()

    def ToPrimitive(self, hint = None):
        return self.DefaultValue(hint)

    def ToObject(self):
        return self

class W__PrimitiveObject(W_BasicObject):
    def __init__(self, primitive_value):
        W_BasicObject.__init__(self)
        self._primitive_value_ = _w(primitive_value)

    def PrimitiveValue(self):
        return self._primitive_value_

    def ToString(self):
        return self.PrimitiveValue().ToString()

    def ToNumber(self):
        return self.PrimitiveValue().ToNumber()

class W_BooleanObject(W__PrimitiveObject):
    _class_ = 'Boolean'

class W_NumericObject(W__PrimitiveObject):
    _class_ = 'Number'

class W_StringObject(W__PrimitiveObject):
    _class_ = 'String'
    def __init__(self, primitive_value):
        W__PrimitiveObject.__init__(self, primitive_value)
        length = len(self._primitive_value_.ToString())
        self._set_property('length', _w(length), DONT_ENUM | DONT_DELETE | READ_ONLY )

class W_DateObject(W__PrimitiveObject):
    _class_ = 'Date'

class W__Object(W_BasicObject):
    def ToString(self):
        try:
            res = self.ToPrimitive('String')
        except JsTypeError:
            return "[object %s]" % (self.Class() ,)
        return res.ToString()

class W_ObjectConstructor(W_BasicObject):
    def __init__(self):
        W_BasicObject.__init__(self)

    def ToString(self):
        return "function Object() { [native code] }"

    def IsCallable(self):
        return True

    def Call(self, args=[], this=None):
        return self.Construct(args)

    def Construct(self, args=[]):
        if len(args) >= 1 and not isnull_or_undefined(args[0]):
            return args[0].ToObject()

        obj = W__Object()
        return obj

class W_BasicFunction(W_BasicObject):
    _class_ = 'Function'
    _type_ = 'function'
    #_immutable_fields_ = ['_context_']

    def __init__(self):
        W_BasicObject.__init__(self)

    def Call(self, args=[], this=None):
        raise NotImplementedError(self.__class__)

    # 13.2.2
    def Construct(self, args=[]):
        obj = W__Object()
        proto = self.Get('prototype')
        if isinstance(proto, W_BasicObject):
            obj._prototype_ = proto
        else:
            # would love to test this
            # but I fail to find a case that falls into this
            obj._prototype_ = W__Object._prototype_


        try: #this is a hack to be compatible to spidermonkey
            self.Call(args, this=obj)
        except ReturnException, e:
            result = e.value
            if isinstance(result, W_BasicObject):
                return result
        return obj

    def IsCallable(self):
        return True

    def Scope(self):
        return self._context_

class W_FunctionConstructor(W_BasicFunction):
    def __init__(self, ctx):
        W_BasicFunction.__init__(self, ctx)

    def ToString(self):
        return "function Function() { [native code] }"

    def Call(self, args=[], this=None):
        from js.jsparser import parse
        from js.jscode import JsCode
        from js.astbuilder import make_ast_builder

        # 15.3.2.1
        functioncode = "function () { }"
        tam = len(args)
        if tam >= 1:
            fbody  = args[tam-1].ToString()
            argslist = []
            for i in range(tam-1):
                argslist.append(args[i].ToString())
            fargs = ','.join(argslist)
            functioncode = "return function (%s) {%s}"%(fargs, fbody)
        #remove program and sourcelements node
        funcnode = parse(functioncode).children[0].children[0]
        builder = make_ast_builder()
        ast = builder.dispatch(funcnode)
        bytecode = JsCode()
        ast.emit(bytecode)
        func = bytecode.make_js_function()
        func2 = func.run(self._context_)
        return func2

    # TODO
    def Construct(self, args=[]):
        return self.Call(args, this=None)

# 15.7.2
class W_NumberConstructor(W_BasicFunction):
    # 15.7.1.1
    def Call(self, args=[], this=None):
        if len(args) >= 1 and not isnull_or_undefined(args[0]):
            return _w(args[0].ToNumber())
        elif len(args) >= 1 and args[0] is w_Undefined:
            return _w(NAN)
        else:
            return _w(0.0)

    # 15.7.2.1
    def Construct(self, args=[]):
        return self.Call(args).ToObject()

# 15.5.2
class W_StringConstructor(W_BasicFunction):
    def Call(self, args=[], this=None):
        if len(args) >= 1:
            return W_String(args[0].ToString())
        else:
            return W_String('')

    def Construct(self, args=[]):
        return self.Call(args).ToObject()

# 15.6.2
class W_BooleanConstructor(W_BasicFunction):
    def Call(self, args=[], this=None):
        if len(args) >= 1 and not isnull_or_undefined(args[0]):
            return _w(args[0].ToBoolean())
        else:
            return _w(False)

    def Construct(self, args=[]):
        return self.Call(args).ToObject()

# 15.9.2
class W_DateConstructor(W_BasicFunction):
    def Call(self, args=[], this=None):
        import time
        return W_DateObject(_w(int(time.time()*1000)))

    # 15.7.2.1
    def Construct(self, args=[]):
        return self.Call(args).ToObject()


class W__Function(W_BasicFunction):
    _immutable_fields_ = ['_function_']

    def __init__(self, function, context):
        W_BasicFunction.__init__(self)
        self._function_ = function
        self._context_ = context

    def Call(self, args=[], this=None):
        f = self._function_
        scope = self.Scope()

        from js.execution_context import FunctionExecutionContext
        ctx = FunctionExecutionContext(f, this, args, scope)
        result = ctx.run()
        return result

    def ToString(self):
        return self._function_.ToString()

class W_Arguments(W_BasicObject):
    def tolist(self):
        l = []
        for i in range(self.length):
            l.append(self._get_property_value(str(i)))
        return l

    @jit.unroll_safe
    def __init__(self, callee, args):
        W_BasicObject.__init__(self)
        self._delete_property('prototype')
        #self.Put('callee', callee)
        self.Put('length', W_IntNumber(len(args)))
        for i in range(len(args)):
            self.Put(str(i), args[i])
        self.length = len(args)

class W_ArrayConstructor(W_BasicObject):
    def IsCallable(self):
        return True

    def Call(self, args=[], this=None):
        if len(args) == 1 and isinstance(args[0], W_Number):
            array = W__Array()
        else:
            array = W__Array()
            for index, obj in enumerate(args):
                array.Put(str(index), obj)
        return array

    def Construct(self, args=[]):
        return self.Call(args)

class W__Array(W_BasicObject):
    _class_ = 'Array'
    length = r_uint(0)

    def __init__(self):
        W_BasicObject.__init__(self)
        self.Put('length', _w(0), flags = DONT_DELETE)

    def set_length(self, newlength):
        if newlength < self.length:
            i = newlength
            while i < self.length:
                key = str(i)
                if key in self._get_property_keys():
                    self._delete_property(key)
                i += 1

        self.length = intmask(newlength)
        self._set_property_value('length', _w(self.length))

    def Put(self, P, V, flags = 0):
        if not self.CanPut(P): return
        if not self._has_property(P):
            self._set_property(P,V,flags)
        else:
            if P != 'length':
                self._set_property_value(P, V)
            else:
                length = V.ToUInt32()
                if length != V.ToNumber():
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

# 15.8
class W_Math(W__Object):
    _class_ = 'Math'

class W_Boolean(W_Primitive):
    _immutable_fields_ = ['_boolval_']
    _type_ = 'boolean'

    def __init__(self, boolval):
        W_Primitive.__init__(self)
        self._boolval_ = bool(boolval)

    def __repr__(self):
        return 'W_Bool(%s)' % (str(self._boolval_), )

    def ToObject(self):
        return W_BooleanObject(self)

    def ToString(self):
        if self._boolval_ == True:
            return "true"
        return "false"

    def ToNumber(self):
        if self._boolval_ == True:
            return 1.0
        return 0.0

    def ToBoolean(self):
        return self._boolval_

class W_String(W_Primitive):
    _immutable_fields_ = ['_strval_']
    _type_ = 'string'

    def __init__(self, strval):
        assert isinstance(strval, str)
        W_Primitive.__init__(self)
        self._strval_ = strval

    def __repr__(self):
        return 'W_String(%s)' % (repr(self._strval_),)

    def ToObject(self):
        return W_StringObject(self)

    def ToString(self):
        return self._strval_

    def ToBoolean(self):
        if len(self._strval_) == 0:
            return False
        else:
            return True

    def ToNumber(self):
        if not self._strval_:
            return 0.0
        try:
            return float(self._strval_)
        except ValueError:
            try:
                return float(int(self._strval_, 16))
            except ValueError:
                try:
                    return float(int(self._strval_, 8))
                except ValueError:
                    return NAN

class W_Number(W_Primitive):
    """ Base class for numbers, both known to be floats
    and those known to be integers
    """
    _type_ = 'number'

    # 9.9
    def ToObject(self):
        return W_NumericObject(self)

    def ToBoolean(self):
        num = self.ToNumber()
        if isnan(num):
            return False
        return bool(num)

    def ToInt32(self):
        return r_int32(self.ToInteger())

    def ToUInt32(self):
        return r_uint32(self.ToInteger())

class W_IntNumber(W_Number):
    _immutable_fields_ = ['_intval_']
    """ Number known to be an integer
    """
    def __init__(self, intval):
        W_Number.__init__(self)
        self._intval_ = intmask(intval)

    def __repr__(self):
        return 'W_IntNumber(%s)' % (self._intval_,)

    def ToInteger(self):
        return self._intval_

    def ToNumber(self):
        # XXX
        return float(self._intval_)

    def ToString(self):
        # XXX incomplete, this doesn't follow the 9.8.1 recommendation
        return str(self.ToInteger())

    def __eq__(self, other):
        return self._intval_ == other._intval_

def r_int32(n):
    return intmask(rffi.cast(rffi.INT, n))

def r_uint32(n):
    return intmask(rffi.cast(rffi.UINT, n))

class W_FloatNumber(W_Number):
    #_immutable_fields_ = ['_floatval_']
    """ Number known to be a float
    """
    def __init__(self, floatval):
        assert isinstance(floatval, float)
        W_Number.__init__(self)
        self._floatval_ = float(floatval)

    def __repr__(self):
        return 'W_FloatNumber(%s)' % (self._floatval_,)

    def ToString(self):
        # XXX incomplete, this doesn't follow the 9.8.1 recommendation
        if isnan(self._floatval_):
            return 'NaN'
        if isinf(self._floatval_):
            if self._floatval_ > 0:
                return 'Infinity'
            else:
                return '-Infinity'
        res = ''
        try:
            res = formatd(self._floatval_, 'g', 10)
        except OverflowError:
            raise

        if len(res) > 3 and (res[-3] == '+' or res[-3] == '-') and res[-2] == '0':
            cut = len(res) - 2
            assert cut >= 0
            res = res[:cut] + res[-1]
        return res

    def ToNumber(self):
        return self._floatval_

    def ToInteger(self):
        if isnan(self._floatval_):
            return 0

        if self._floatval_ == 0 or isinf(self._floatval_):
            return self._floatval_

        return intmask(int(self._floatval_))

    def __eq__(self, other):
        return self._floatval_ == other._floatval_

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

class W_List(object):
    def __init__(self, values):
        self.values = values

    def ToList(self):
        return self.values

from pypy.rlib.objectmodel import specialize

@specialize.argtype(0)
def _w(value):
    if isinstance(value, W_Root):
        return value
    elif isinstance(value, bool):
        return newbool(value)
    elif isinstance(value, int):
        return W_IntNumber(value)
    elif isinstance(value, float):
        return W_FloatNumber(value)
    elif isinstance(value, str):
        return W_String(value)
    elif value is None:
        return w_Null
    raise TypeError(value)

