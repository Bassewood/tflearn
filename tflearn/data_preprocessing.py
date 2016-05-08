# -*- coding: utf-8 -*-
from __future__ import division, print_function, absolute_import

import numpy as np
import tensorflow as tf

_EPSILON = 1e-8


class DataPreprocessing(object):
    """ Data Preprocessing.

    Manage real-time data preprocessing.

    """

    def __init__(self, name="DataPreprocessing"):
        self.methods = []
        self.args = []
        self.session = None
        # Data Persistence
        with tf.name_scope(name) as scope:
            self.scope = scope
        self.global_mean = self.PersistentParameter(scope, name="mean")
        self.global_std = self.PersistentParameter(scope, name="std")

    def apply(self, batch):
        for i, m in enumerate(self.methods):
            if self.args[i]:
                batch = m(batch, *self.args[i])
            else:
                batch = m(batch)
        return batch

    def initialize(self, dataset, session, limit=None):
        """ Initialize preprocessing methods that pre-requires
        calculation over entire dataset. """
        if self.global_mean.is_required:
            # If a value is already provided, it has priority
            if self.global_mean.value is not None:
                self.global_mean.assign(self.global_mean.value, session)
            # Otherwise, if it has not been restored, compute it
            if not self.global_mean.is_restored(session):
                print("---------------------------------")
                print("Preprocessing... Calculating mean over all dataset "
                      "(this may take long)...")
                self._compute_global_mean(dataset, session, limit)
                print("Mean: " + str(self.global_mean.value) + " (To avoid "
                      "repetitive computation, add it to argument 'mean' of "
                      "`add_featurewise_zero_center`)")
        if self.global_std.is_required:
            # If a value is already provided, it has priority
            if self.global_std.value is not None:
                self.global_std.assign(self.global_std.value, session)
            # Otherwise, if it has not been restored, compute it
            if not self.global_std.is_restored(session):
                print("---------------------------------")
                print("Preprocessing... Calculating std over all dataset "
                      "(this may take long)...")
                self._compute_global_std(dataset, session, limit)
                print("STD: " + str(self.global_std.value) + " (To avoid "
                      "repetitive computation, add it to argument 'std' of "
                      "`add_featurewise_stdnorm`)")

    # -----------------------
    #  Preprocessing Methods
    # -----------------------

    def add_samplewise_zero_center(self):
        """ add_samplewise_zero_center.

        Zero center each sample by subtracting it by its mean.

        Returns:
            Nothing.

        """
        self.methods.append(self._samplewise_zero_center)
        self.args.append(None)

    def add_samplewise_stdnorm(self):
        """ add_samplewise_stdnorm.

        Scale each sample with its standard deviation.

        Returns:
            Nothing.

        """
        self.methods.append(self._samplewise_stdnorm)
        self.args.append(None)

    def add_featurewise_zero_center(self, mean=None):
        """ add_samplewise_zero_center.

        Zero center every sample with specified mean. If not specified,
        the mean is evaluated over all samples.

        Arguments:
            mean: `float` (optional). Provides a custom mean. If none
                provided, it will be automatically caluclated based on
                the training dataset. Default: None.

        Returns:
            Nothing.

        """
        self.global_mean.is_required = True
        self.global_mean.value = mean
        self.methods.append(self._featurewise_zero_center)
        self.args.append(None)

    def add_featurewise_stdnorm(self, std=None):
        """ add_featurewise_stdnorm.

        Scale each sample by the specified standard deviation. If no std
        specified, std is evaluated over all samples data.

        Arguments:
            std: `float` (optional). Provides a custom standard derivation.
                If none provided, it will be automatically caluclated based on
                the training dataset. Default: None.

        Returns:
            Nothing.

        """
        self.global_std.is_required = True
        self.global_std.value = std
        self.methods.append(self._featurewise_stdnorm)
        self.args.append(None)

    def add_zca_whitening(self):
        """ add_zca_whitening.

        ZCA Whitening.

        """
        raise NotImplementedError

    # ---------------------------
    #  Preprocessing Calculation
    # ---------------------------

    def _samplewise_zero_center(self, batch):
        for i in range(len(batch)):
            batch[i] -= np.mean(batch[i], axis=0)
        return batch

    def _samplewise_stdnorm(self, batch):
        for i in range(len(batch)):
            batch[i] /= (np.std(batch[i], axis=0) + _EPSILON)
        return batch

    def _featurewise_zero_center(self, batch):
        for i in range(len(batch)):
            batch[i] -= self.global_mean.value
        return batch

    def _featurewise_stdnorm(self, batch):
        for i in range(len(batch)):
            batch[i] /= (self.global_std.value + _EPSILON)
        return batch

    # ---------------------------------------
    #  Calulation with Persistent Parameters
    # ---------------------------------------

    def _compute_global_mean(self, dataset, session, limit=None):
        """ Compute mean of a dataset. A limit can be specified for faster
        computation, considering only 'limit' first elements. """
        _dataset = dataset
        mean = 0.
        if isinstance(limit, int):
            _dataset = _dataset[:limit]
        if isinstance(_dataset, np.ndarray):
            mean = np.mean(_dataset)
        else:
            # Iterate in case of non numpy data
            for i in range(len(dataset)):
                mean += np.mean(dataset[i]) / len(dataset)
        self.global_mean.assign(mean, session)
        return mean

    def _compute_global_std(self, dataset, session, limit=None):
        """ Compute std of a dataset. A limit can be specified for faster
        computation, considering only 'limit' first elements. """
        _dataset = dataset
        std = 0.
        if isinstance(limit, int):
            _dataset = _dataset[:limit]
        if isinstance(_dataset, np.ndarray):
            std = np.std(_dataset)
        else:
            for i in range(len(dataset)):
                std += np.std(dataset[i]) / len(dataset)
        self.global_std.assign(std, session)
        return std

    # -----------------------
    #  Persistent Parameters
    # -----------------------

    class PersistentParameter:
        """ Create a persistent variable that will be stored into the Graph.
        """
        def __init__(self, scope, name):
            self.is_required = False
            with tf.name_scope(scope):
                # One variable contains the value
                self.var = tf.Variable(0., trainable=False, name=name)
                # Another one check if it has been restored or not
                self.var_r = tf.Variable(False, trainable=False,
                                         name=name+"_r")
            # RAM saved vars for faster access
            self.restored = False
            self.value = None

        def is_restored(self, session):
            if self.var_r.eval(session=session):
                self.value = self.var.eval(session=session)
                return True
            else:
                return False

        def assign(self, value, session):
            session.run(tf.assign(self.var, value, validate_shape=False))
            self.value = value
            session.run(self.var_r.assign(True))
            self.restored = True


class ImagePreprocessing(DataPreprocessing):

    """ Image Preprocessing.

    Manage real-time image pre-processing.

    """

    def __init__(self):
        super(ImagePreprocessing, self).__init__()
        self.global_mean_pc = False
        self.global_std_pc = False

    # -----------------------
    #  Preprocessing Methods
    # -----------------------

    def add_image_normalization(self):
        self.methods.append(self._normalize_image)
        self.args.append(None)

    def resize(self, height, width):
        raise NotImplementedError

    def blur(self):
        raise NotImplementedError

    # -----------------------
    #  Preprocessing Methods
    # -----------------------

    def _normalize_image(self, batch):
        return batch / 255.

    # ----------------------------------------------
    #  Preprocessing Methods (Overwrited from Base)
    # ----------------------------------------------

    def add_samplewise_zero_center(self, per_channel=False):
        """ add_samplewise_zero_center.

        Zero center each sample by subtracting it by its mean.

        Arguments:
            per_channel: `bool`. If True, apply per channel mean.

        Returns:
            Nothing.

        """
        self.methods.append(self._samplewise_zero_center)
        self.args.append([per_channel])

    def add_samplewise_stdnorm(self, per_channel=False):
        """ add_samplewise_stdnorm.

        Scale each sample with its standard deviation.

        Arguments:
            per_channel: `bool`. If True, apply per channel std.

        Returns:
            Nothing.

        """
        self.methods.append(self._samplewise_stdnorm)
        self.args.append([per_channel])

    def add_featurewise_zero_center(self, mean=None, per_channel=False):
        """ add_samplewise_zero_center.

        Zero center every sample with specified mean. If not specified,
        the mean is evaluated over all samples.

        Arguments:
            mean: `float` (optional). Provides a custom mean. If none
                provided, it will be automatically caluclated based on
                the training dataset. Default: None.
            per_channel: `bool`. If True, compute mean per color channel.

        Returns:
            Nothing.

        """
        self.global_mean.is_required = True
        self.global_mean.value = mean
        if per_channel:
            self.global_mean_pc = True
        self.methods.append(self._featurewise_zero_center)
        self.args.append(None)

    def add_featurewise_stdnorm(self, std=None, per_channel=False):
        """ add_featurewise_stdnorm.

        Scale each sample by the specified standard deviation. If no std
        specified, std is evaluated over all samples data.

        Arguments:
            std: `float` (optional). Provides a custom standard derivation.
                If none provided, it will be automatically caluclated based on
                the training dataset. Default: None.
            per_channel: `bool`. If True, compute std per color channel.

        Returns:
            Nothing.

        """
        self.global_std.is_required = True
        self.global_std.value = std
        if per_channel:
            self.global_std_pc = True
        self.methods.append(self._featurewise_stdnorm)
        self.args.append(None)

    # --------------------------------------------------
    #  Preprocessing Calculation (Overwrited from Base)
    # --------------------------------------------------

    def _samplewise_zero_center(self, batch, per_channel=False):
        for i in range(len(batch)):
            if not per_channel:
                batch[i] -= np.mean(batch[i])
            else:
                batch[i] -= np.mean(batch[i], axis=(0, 1, 2), keepdims=True)
        return batch

    def _samplewise_stdnorm(self, batch, per_channel=False):
        for i in range(len(batch)):
            if not per_channel:
                batch[i] /= (np.std(batch[i]) + _EPSILON)
            else:
                batch[i] /= (np.std(batch[i], axis=(0, 1, 2),
                                    keepdims=True) + _EPSILON)
        return batch

    # --------------------------------------------------------------
    #  Calulation with Persistent Parameters (Overwrited from Base)
    # --------------------------------------------------------------

    def _compute_global_mean(self, dataset, session, limit=None):
        """ Compute mean of a dataset. A limit can be specified for faster
        computation, considering only 'limit' first elements. """
        _dataset = dataset
        mean = 0.
        if isinstance(limit, int):
            _dataset = _dataset[:limit]
        if isinstance(_dataset, np.ndarray) and not self.global_mean_pc:
            mean = np.mean(_dataset)
        else:
            # Iterate in case of non numpy data
            for i in range(len(dataset)):
                if not self.global_mean_pc:
                    mean += np.mean(dataset[i]) / len(dataset)
                else:
                    mean += (np.mean(dataset[i], axis=(0, 1),
                             keepdims=True) / len(dataset))[0][0]
        self.global_mean.assign(mean, session)
        return mean

    def _compute_global_std(self, dataset, session, limit=None):
        """ Compute std of a dataset. A limit can be specified for faster
        computation, considering only 'limit' first elements. """
        _dataset = dataset
        std = 0.
        if isinstance(limit, int):
            _dataset = _dataset[:limit]
        if isinstance(_dataset, np.ndarray) and not self.global_std_pc:
            std = np.std(_dataset)
        else:
            for i in range(len(dataset)):
                if not self.global_std_pc:
                    std += np.std(dataset[i]) / len(dataset)
                else:
                    std += (np.std(dataset[i], axis=(0, 1),
                             keepdims=True) / len(dataset))[0][0]
        self.global_std.assign(std, session)
        return std


class SequencePreprocessing(DataPreprocessing):

    def __init__(self):
        super(SequencePreprocessing, self).__init__()

    def sequence_padding(self):
        raise NotImplementedError
