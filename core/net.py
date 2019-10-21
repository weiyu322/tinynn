"""Feed-forward Neural Network class."""

import copy

import numpy as np


class Net(object):

    def __init__(self, layers):
        self.layers = layers
        self._phase = "TRAIN"

    def forward(self, inputs):
        for layer in self.layers:
            inputs = layer.forward(inputs)
        return inputs

    def backward(self, grad):
        # back propagation
        layer_grads = []
        for layer in reversed(self.layers):
            grad = layer.backward(grad)
            layer_grads.append(copy.copy(layer.grads))

        # return structured gradients
        struct_grad = StructuredParam(layer_grads[::-1])
        # keep the gradient w.r.t the input
        struct_grad.wrt_input = grad
        return struct_grad

    @property
    def params(self):
        return StructuredParam([l.params for l in self.layers])

    @params.setter
    def params(self, params):
        self.params.values = params.values

    def get_phase(self):
        return self._phase

    def set_phase(self, phase):
        for layer in self.layers:
            layer.set_phase(phase)
        self._phase = phase

    def init_params(self, input_shape):
        """Manually init parameters by letting data forward throught the network."""
        # TODO: better way to do this?
        fake = np.ones((1, *input_shape))
        self.forward(fake)


class StructuredParam(object):
    """A helper class represents network parameters or gradients."""

    def __init__(self, layer_data):
        self.layer_data = layer_data

    @property
    def values(self):
        return np.array([v for d in self.layer_data for v in d.values()])

    @values.setter
    def values(self, values):
        i = 0
        for d in self.layer_data:
            for name in d.keys():
                d[name] = values[i]
                i += 1

    @property
    def shape(self):
        return self._get_shape()

    def _get_shape(self):
        shape = list()
        for d in self.layer_data:
            l_shape = dict()
            for k, v in d.items():
                l_shape[k] = v.shape
            shape.append(l_shape)
        shape = tuple(shape)
        return shape

    def __repr__(self):
        cont = "%s with shape\n" % self.__class__.__name__
        cont += ("-" * 10 + "\n")
        cont += "\n".join([str(s) for s in self.shape])
        cont += ("\n" + "-" * 10)
        return cont

    def clip(self, min_=None, max_=None):
        self.values = [v.clip(min_, max_)for v in self.values]

    @staticmethod
    def _ensure_values(obj):
        if isinstance(obj, StructuredParam):
            obj = obj.values
        return obj

    def __add__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self.values + self._ensure_values(other)
        return obj

    def __radd__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self._ensure_values(other) + self.values
        return obj

    def __iadd__(self, other):
        self.values += self._ensure_values(other)
        return self

    def __sub__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self.values - self._ensure_values(other)
        return obj

    def __rsub__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self._ensure_values(other) - self.values
        return obj

    def __isub__(self, other):
        other = self._ensure_values(other)
        self.values -= self._ensure_values(other)
        return self

    def __mul__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self.values * self._ensure_values(other)
        return obj

    def __rmul__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self._ensure_values(other) * self.values
        return obj

    def __imul__(self, other):
        self.values *= self._ensure_values(other)
        return self

    def __truediv__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self.values / self._ensure_values(other)
        return obj

    def __rtruediv__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self._ensure_values(other) / self.values
        return obj

    def __itruediv__(self, other):
        self.values /= self._ensure_values(other)
        return self

    def __pow__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self.values ** self._ensure_values(other)
        return obj

    def __ipow__(self, other):
        self.values **= self._ensure_values(other)
        return self

    def __neg__(self):
        obj = copy.deepcopy(self)
        obj.values = -self.values
        return obj

    def __len__(self):
        return len(self.values)

    def __lt__(self, other):
        obj = copy.deepcopy(self)
        other = self._ensure_values(other)

        if isinstance(other, float):
            obj.values = [v < other for v in self.values]
        else:
            obj.values = [v < other[i] for i, v in enumerate(self.values)]
        return obj

    def __gt__(self, other):
        obj = copy.deepcopy(self)
        other = self._ensure_values(other)

        if isinstance(other, float):
            obj.values = [v > other for v in self.values]
        else:
            obj.values = [v > other[i] for i, v in enumerate(self.values)]
        return obj

    def __and__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self._ensure_values(other) & self.values
        return obj

    def __or__(self, other):
        obj = copy.deepcopy(self)
        obj.values = self._ensure_values(other) | self.values
        return obj
