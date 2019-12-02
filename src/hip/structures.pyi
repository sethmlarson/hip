class _ParamNoValue(object):
    def __bool__(self) -> bool:
        # We want this sentinel to evaluate as 'falsy'
        return False
    def __repr__(self) -> str:
        return "hip.PARAM_NO_VALUE"
    __str__ = __repr__

PARAM_NO_VALUE = _ParamNoValue()
