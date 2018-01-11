from distutils.version import LooseVersion

import tensorflow as tf

TENSORFLOW_VERSION = LooseVersion(tf.__version__)


def tf_concat(axis, values, **kwargs):
    if TENSORFLOW_VERSION >= LooseVersion('1.0'):
        return tf.concat(values, axis, **kwargs)
    else:
        return tf.concat(axis, values, **kwargs)
