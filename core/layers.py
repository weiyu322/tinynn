"""Network layers and activation layers."""

import numpy as np

from core.initializer import XavierUniformInit
from core.initializer import ZerosInit


class Layer(object):

    def __init__(self, name):
        self.name = name

        self.params, self.grads = {}, {}
        self.is_training = True

    def forward(self, inputs):
        raise NotImplementedError

    def backward(self, grad):
        raise NotImplementedError

    def set_phase(self, phase):
        self.is_training = True if phase == "TRAIN" else False


class Dense(Layer):

    def __init__(self,
                 num_out,
                 num_in=None,
                 w_init=XavierUniformInit(),
                 b_init=ZerosInit()):
        super().__init__("Linear")
        self.initializers = {"w": w_init, "b": b_init}
        self.shapes = {"w": [num_in, num_out], "b": [1, num_out]}
        self.params = {"w": None, "b": None}

        self.is_init = False
        if num_in is not None:
            self._init_parameters(num_in)

        self.inputs = None

    def forward(self, inputs):
        # lazy initialize
        if not self.is_init:
            self._init_parameters(inputs.shape[1])

        self.inputs = inputs
        return inputs @ self.params["w"] + self.params["b"]

    def backward(self, grad):
        self.grads["w"] = self.inputs.T @ grad
        self.grads["b"] = np.sum(grad, axis=0)
        return grad @ self.params["w"].T

    def _init_parameters(self, input_size):
        self.shapes["w"][0] = input_size
        self.params["w"] = self.initializers["w"](shape=self.shapes["w"])
        self.params["b"] = self.initializers["b"](shape=self.shapes["b"])
        self.is_init = True


class Conv2D(Layer):
    """
    Implement 2D convolution layer
    :param kernel: A list/tuple of int that has length 4 (height, width,
        in_channels, out_channels)
    :param stride: A list/tuple of int that has length 2 (height, width)
    :param padding: String ["SAME", "VALID", "FULL"]
    :param w_init: weight initializer
    :param b_init: bias initializer
    """
    def __init__(self,
                 kernel,
                 stride=(1, 1),
                 padding="SAME",
                 w_init=XavierUniformInit(),
                 b_init=ZerosInit()):
        super().__init__("Conv2D")

        # verify arguments
        assert len(kernel) == 4
        assert len(stride) == 2
        assert padding in ("FULL", "SAME", "VALID")

        self.kernel_shape = kernel
        self.stride_shape = stride
        self.initializers = {"w": w_init, "b": b_init}

        # calculate padding needed for this layer
        k_h, k_w = kernel[:2]
        self.pad = self._get_padding(k_h, k_w, padding)

        self.is_init = False

    def forward(self, inputs):
        """
        Accelerate convolution via im2col trick.
        An example (assuming only one channel and one filter):
         input = | 43  16  78 |         kernel = | 4  6 |
          (X)    | 34  76  95 |                  | 7  9 |
                 | 35   8  46 |
        
        After im2col and kernel flattening:
         col  = | 43  16  34  76 |     kernel = | 4 |
                | 16  78  76  95 |      (W)     | 6 |
                | 34  76  35   8 |              | 7 |
                | 76  95   8  46 |              | 9 |
        """
        # lazy initialization
        if not self.is_init:
            self._init_parameters()

        k_h, k_w, in_c, out_c = self.kernel_shape
        s_h, s_w = self.stride_shape
        pad = self.pad
        # number of incomming channels should match
        assert in_c == inputs.shape[3]

        # step1: zero-padding
        pad_width = ((0, 0), (pad[0], pad[1]), (pad[2], pad[3]), (0, 0))
        X = np.pad(inputs, pad_width=pad_width, mode="constant")

        # step2: im2col
        # padded inputs to column matrix
        col = self._im2col(X, k_h, k_w, s_h, s_w)
        # flatten kernel
        W = self.params["w"].reshape(-1, out_c)  # (k_h * k_w * in_c, out_c)

        # step3: perform convolution by matrix product.
        Z = col @ W

        # step4: reshape output 
        batch_sz, in_h, in_w, _ = X.shape 
        # separate the batch size and feature map dimensions
        Z = Z.reshape(batch_sz, Z.shape[0] // batch_sz, out_c)
        # further divide the feature map in to (h, w) dimension
        out_h = (in_h - k_h) // s_h + 1
        out_w = (in_w - k_w) // s_w + 1
        Z = Z.reshape(batch_sz, out_h, out_w, out_c)

        # plus the bias for every filter
        Z += self.params["b"]

        # save results for backward function
        self.col = col
        self.W = W
        self.X_shape = X.shape
        return Z

    def backward(self, grad):
        """
        Compute gradiens w.r.t layer parameters and backward gradients.
        :param grad: gradients from previous layer 
            with shape (batch_sz, out_h, out_w, out_c)
        :return d_in: gradients to next layers 
            with shape (batch_sz, in_h, in_w, in_c)
        """
        # read size parameters
        k_h, k_w, in_c, out_c = self.kernel_shape
        s_h, s_w = self.stride_shape
        batch_sz, in_h, in_w, in_c = self.X_shape
        pad = self.pad

        # calculate gradients of parameters
        flat_grad = grad.reshape((-1, out_c))
        d_W = self.col.T @ flat_grad
        self.grads["w"] = d_W.reshape(self.kernel_shape)
        self.grads["b"] = np.sum(flat_grad, axis=0)

        # calculate backward gradients
        d_X = grad @ self.W.T
        # cast gradients back to original shape as d_in
        d_in = np.zeros(shape=self.X_shape)
        for i, r in enumerate(range(0, in_h - k_h + 1, s_h)):
            for j, c in enumerate(range(0, in_w - k_w + 1, s_w)):
                patch = d_X[:, i, j, :]
                patch = patch.reshape((batch_sz, k_h, k_w, in_c))
                d_in[:, r:r+k_h, c:c+k_w, :] += patch

        # cut off gradients of padding
        d_in = d_in[:, pad[0]:in_h-pad[1], pad[2]:in_w-pad[3], :]
        return d_in

    @staticmethod
    def _im2col(img, k_h, k_w, s_h, s_w):
        """
        Transform padded image into column matrix.
        :param img: padded inputs of shape (B, in_h, in_w, in_c)
        :param k_h: kernel height
        :param k_w: kernel width
        :param s_h: stride height
        :param s_w: stride width
        :return col: column matrix of shape (B*out_h*out_w, k_h*k_h*inc)
        """
        batch_sz, h, w, in_c = img.shape
        # calculate result feature map size
        out_h = (h - k_h) // s_h + 1
        out_w = (w - k_w) // s_w + 1
        # allocate space for column matrix
        col = np.empty((batch_sz * out_h * out_w, k_h * k_w * in_c))
        # fill in the column matrix
        batch_span = out_w * out_h
        for r in range(out_h):
            r_start = r * s_h
            matrix_r = r * out_w 
            for c in range(out_w):
                c_start = c * s_w
                patch = img[:, r_start: r_start+k_h, c_start: c_start+k_w, :]
                patch = patch.reshape(batch_sz, -1)
                col[matrix_r+c :: batch_span, :] = patch
        return col

    @staticmethod
    def _get_padding(k_h, k_w, mode):
        """
        :param k_h: kernel height 
        :param k_w: kernel width
        :param mode (FULL|VALID|SAME)
            - FULL: to generate maximum sized feature map, allow only one valid
            pixel to be mapped at the corners.
            - VALID: to generate minimal sized feature map, require all kernel
            units mapping to valid input area.
            - SAME: require generated feature map to have the same (or almost
            the same) size as input area.
        :return: list of padding (top, bottom, left, right) in different modes
        """
        if mode == "FULL":
            pad = [k_h - 1, k_w - 1, k_h - 1, k_w - 1]
        elif mode == "VALID":
            pad = [0, 0, 0, 0]
        else:
            # SAME mode
            pad = [(k_h - 1) // 2, (k_h - 1) // 2,
                   (k_w - 1) // 2, (k_w - 1) // 2]
            if k_h % 2 == 0:
                pad[1] += 1
            if k_w % 2 == 0:
                pad[3] += 1
        return pad

    def _init_parameters(self):
        self.params["w"] = self.initializers["w"](self.kernel_shape)
        self.params["b"] = self.initializers["b"](self.kernel_shape[-1])
        self.is_init = True


class MaxPool2D(Layer):

    def __init__(self,
                 pool_size,
                 stride,
                 padding="VALID"):
        """
        Implement 2D max-pooling layer
        :param pool_size: A list/tuple of 2 integers (pool_height, pool_width)
        :param stride: A list/tuple of 2 integers (stride_height, stride_width)
        :param padding: A string ("SAME", "VALID")
        """
        super().__init__("MaxPooling2D")
        # validate arguments
        assert len(pool_size) == 2
        assert len(stride) == 2
        assert padding in ("VALID", "SAME")

        self.pool_size = pool_size
        self.stride = stride
        self.padding_mode = padding

        self.cache = None

    def forward(self, inputs):
        in_n, in_h, in_w, in_c = inputs.shape
        pad = self._get_padding([in_h, in_w], self.pool_size, self.stride,
                                self.padding_mode)
        pad_width = ((0, 0), (pad[0], pad[1]), (pad[2], pad[3]), (0, 0))
        padded = np.pad(inputs, pad_width=pad_width, mode="constant")
        pad_h, pad_w = padded.shape[1:3]
        (s_h, s_w), (pool_h, pool_w) = self.stride, self.pool_size
        out_h, out_w = pad_h // s_h, pad_w // s_w
        patches_list, max_pos_list = list(), list()
        for col in range(0, pad_h, s_h):
            for row in range(0, pad_w, s_w):
                pool = padded[:, col:col + pool_h, row:row + pool_w, :]
                pool = pool.reshape((in_n, -1, in_c))
                max_pos_list.append(np.argmax(pool, axis=1))
                patches_list.append(np.max(pool, axis=1))
        outputs = np.array(patches_list).transpose((1, 0, 2)).reshape(
            (in_n, out_h, out_w, in_c))
        max_pos = np.array(max_pos_list).transpose((1, 0, 2)).reshape(
            (in_n, out_h, out_w, in_c))

        self.cache = {"in_n": in_n, "in_img_size": (in_h, in_w, in_c),
                      "stride": (s_h, s_w), "pad": (pad_h, pad_w),
                      "pool": (pool_h, pool_w), "max_pos": max_pos,
                      "out_img_size": (out_h, out_w, in_c)}
        return outputs

    def backward(self, grad):
        in_n, (in_h, in_w, in_c) = self.cache["in_n"], self.cache["in_img_size"]
        s_h, s_w = self.cache["stride"]
        pad_h, pad_w = self.cache["pad"]
        pool_h, pool_w = self.cache["pool"]

        d_in = np.zeros(shape=(in_n, pad_h, pad_w, in_c))
        for i, col in enumerate(range(0, pad_h, s_h)):
            for j, row in enumerate(range(0, pad_w, s_w)):
                _max_pos = self.cache["max_pos"][:, i, j, :]
                _grad = grad[:, i, j, :]
                mask = np.eye(pool_h * pool_w)[_max_pos].transpose((0, 2, 1))
                region = np.repeat(_grad[:, np.newaxis, :],
                                   pool_h * pool_w, axis=1) * mask
                region = region.reshape((in_n, pool_h, pool_w, in_c))
                d_in[:, col:col + pool_h, row:row + pool_w, :] = region
        return d_in

    def _get_padding(self, input_size, pool_size, stride, mode):
        h_pad = self._get_padding_1d(
            input_size[0], pool_size[0], stride[0], mode)
        w_pad = self._get_padding_1d(
            input_size[1], pool_size[1], stride[1], mode)
        return h_pad + w_pad

    @staticmethod
    def _get_padding_1d(input_size, pool_size, stride, mode):
        if mode == "SAME":
            r = input_size % stride
            if r == 0:
                n_pad = max(pool_size - stride, 0)
            else:
                n_pad = max(pool_size, stride) - r
        else:
            n_pad = 0
        half = n_pad // 2
        pad = [half, half] if n_pad % 2 == 0 else [half, half + 1]
        return pad


class Flatten(Layer):

    def __init__(self):
        super().__init__("Flatten")
        self.input_shape = None

    def forward(self, inputs):
        self.input_shape = inputs.shape
        return inputs.ravel().reshape(inputs.shape[0], -1)

    def backward(self, grad):
        return grad.reshape(self.input_shape)


class Dropout(Layer):

    def __init__(self, keep_prob=0.5):
        super().__init__("Dropout")
        self._keep_prob = keep_prob
        self._multiplier = None

    def forward(self, inputs):
        if self.is_training:
            multiplier = np.random.binomial(
                1, self._keep_prob, size=inputs.shape)
            self._multiplier = multiplier / self._keep_prob
            outputs = inputs * self._multiplier
        else:
            outputs = inputs
        return outputs

    def backward(self, grad):
        assert self.is_training is True
        return grad * self._multiplier


class Activation(Layer):

    def __init__(self, name):
        super().__init__(name)
        self.inputs = None

    def forward(self, inputs):
        self.inputs = inputs
        return self.func(inputs)

    def backward(self, grad):
        return self.derivative_func(self.inputs) * grad

    def func(self, x):
        raise NotImplementedError

    def derivative_func(self, x):
        raise NotImplementedError


class Sigmoid(Activation):

    def __init__(self):
        super().__init__("Sigmoid")

    def func(self, x):
        return 1.0 / (1.0 + np.exp(-x))

    def derivative_func(self, x):
        return self.func(x) * (1.0 - self.func(x))


class Softplus(Activation):

    def __init__(self):
        super().__init__("Softplus")

    def func(self, x):
        return np.log(1.0 + np.exp(-np.abs(x))) + np.maximum(x, 0.0)

    def derivative_func(self, x):
        return 1.0 / (1.0 + np.exp(-x))


class Tanh(Activation):

    def __init__(self):
        super().__init__("Tanh")

    def func(self, x):
        return np.tanh(x)

    def derivative_func(self, x):
        return 1.0 - self.func(x) ** 2


class ReLU(Activation):

    def __init__(self):
        super().__init__("ReLU")

    def func(self, x):
        return np.maximum(x, 0.0)

    def derivative_func(self, x):
        return x > 0.0


class LeakyReLU(Activation):

    def __init__(self, slope=0.2):
        super().__init__("LeakyReLU")
        self._slope = slope

    def func(self, x):
        x = x.copy()
        x[x < 0.0] *= self._slope
        return x

    def derivative_func(self, x):
        dx = np.ones_like(x)
        dx[x < 0.0] = self._slope
        return dx
