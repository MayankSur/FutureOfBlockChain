# Copyright (C) 2018 NuCypher
#
# This file is part of nufhe.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import numpy
from reikna import cluda

from .lwe import LweSampleArray
from .api_low_level import (
    NuFHEParameters, NuFHESecretKey, NuFHECloudKey, encrypt, decrypt, empty_ciphertext)
from .performance import PerformanceParameters
from . import gates
from .random_numbers import DeterministicRNG


class Context:
    """
    An object encapuslating an execution environment on a GPU.

    :param rng: a random number generator which will be used wherever randomness is required.
        Can be an instance of one of the :ref:`random-number-generators`
        (:py:class:`DeterministicRNG` by default).
    :param api: the GPGPU backend to use, one of ``None``, ``"CUDA"`` and ``"OpenCL"``.
        If ``None`` is given, an arbitrary available backend will be chosen.
    :param interactive: if ``True``, an interactive dialogue will be shown
        allowing one to choose the GPGPU device to use.
        If ``False``, the first device satisfying the filters (see below) will be chosen.
    :param include_devices: a list of strings; only devices with one of the strings
        present in the name will be included.
    :param exclude_devices: a list of strings; devices with one of the strings
        present in the name will be excluded.
    :param include_platforms: a list of strings; only platforms with one of the strings
        present in the name will be included.
    :param exclude_platforms: a list of strings; platforms with one of the strings
        present in the name will be excluded.
    """

    def __init__(
            self, rng=None,
            api=None, interactive=False,
            include_devices=None, exclude_devices=None,
            include_platforms=None, exclude_platforms=None):

        if rng is None:
            rng = DeterministicRNG()

        api_funcs = {
            None: cluda.any_api,
            'CUDA': cluda.cuda_api,
            'OpenCL': cluda.ocl_api,
            }
        api = api_funcs[api]()
        thread = api.Thread.create(
            interactive=interactive,
            device_filters=dict(
                include_devices=include_devices,
                exclude_devices=exclude_devices,
                include_platforms=include_platforms,
                exclude_platforms=exclude_platforms))

        self.rng = rng
        self.thread = thread

    def make_secret_key(self, **params):
        """
        Creates a secret key, with ``params`` used to
        initialize a :py:class:`NuFHEParameters` object.

        The low-level analogue: :py:meth:`NuFHESecretKey.from_rng`.

        :returns: a :py:class:`NuFHESecretKey` object.
        """
        nufhe_params = NuFHEParameters(**params)
        return NuFHESecretKey.from_rng(self.thread, nufhe_params, self.rng)

    def make_cloud_key(self, secret_key: NuFHESecretKey):
        """
        Creates a cloud key matching the given secret key.

        The low-level analogue: :py:meth:`NuFHECloudKey.from_rng`.

        :returns: a :py:class:`NuFHECloudKey` object.
        """
        return NuFHECloudKey.from_rng(self.thread, secret_key.params, self.rng, secret_key)

    def make_key_pair(self, **params):
        """
        Creates a pair of a secret key and a matching cloud key.

        The low-level analogue: :py:func:`make_key_pair`.

        :returns: a tuple of a :py:class:`NuFHESecretKey` and a :py:class:`NuFHECloudKey` objects.
        """
        secret_key = self.make_secret_key(**params)
        cloud_key = self.make_cloud_key(secret_key)
        return secret_key, cloud_key

    def encrypt(self, secret_key: NuFHESecretKey, message):
        """
        Encrypts a message (a list or a ``numpy`` array treated as an array of booleans).

        The low-level analogue: :py:func:`encrypt`.

        :returns: an :py:class:`LweSampleArray` object with the same `shape` as the given array.
        """
        return encrypt(self.thread, self.rng, secret_key, message)

    def decrypt(self, secret_key: NuFHESecretKey, ciphertext: LweSampleArray):
        """
        Decrypts a message.

        The low-level analogue: :py:func:`decrypt`.

        :returns: a ``numpy.ndarray`` object of the type ``numpy.bool``
            and the same `shape` as ``ciphertext``.
        """
        return decrypt(self.thread, secret_key, ciphertext)

    def make_virtual_machine(
            self, cloud_key: NuFHECloudKey, perf_params: PerformanceParameters=None):
        """
        Creates an FHE "virtual machine" which can execute logical gates using the given cloud key.
        Optionally, one can pass a :py:class:`PerformanceParameters` object which will be
        specialized for the GPU device of the context and used in all the gate calls.

        :returns: a :py:class:`~nufhe.api_high_level.VirtualMachine` object.
        """
        return VirtualMachine(self.thread, cloud_key, perf_params=perf_params)

    def load_ciphertext(self, file):
        """
        Load a ciphertext (a :py:class:`LweSampleArray` object) serialized with
        :py:meth:`LweSampleArray.dump` into the context memory space.

        The low-level analogue: :py:meth:`LweSampleArray.load`.

        :returns: an :py:class:`LweSampleArray` object
        """
        return LweSampleArray.load(file, self.thread)

    def load_secret_key(self, file):
        """
        Load a secret key (a :py:class:`NuFHESecretKey` object) serialized with
        :py:meth:`NuFHESecretKey.dump` into the context memory space.

        The low-level analogue: :py:meth:`NuFHESecretKey.load`.

        :returns: a :py:class:`NuFHESecretKey` object
        """
        return NuFHESecretKey.load(file, self.thread)

    def load_cloud_key(self, file):
        """
        Load a secret key (a :py:class:`NuFHECloudKey` object) serialized with
        :py:meth:`NuFHECloudKey.dump` into the context memory space.

        The low-level analogue: :py:meth:`NuFHECloudKey.load`.

        :returns: a :py:class:`NuFHECloudKey` object
        """
        return NuFHECloudKey.load(file, self.thread)


class VirtualMachine:
    """
    A fully encrypted virtual machine capable of executing gates on ciphertexts
    (:py:class:`~nufhe.LweSampleArray` objects) using an encapsulated cloud key.

    .. method:: gate_<operator>(*args, dest: LweSampleArray=None)

        Calls one of :ref:`logical-gates`, using the context, the cloud key,
        and the performance parameters of the virtual machine.

        If ``dest`` is ``None``, creates a new ciphertext and uses it
        to store the output of the gate;
        otherwise ``dest`` is used for that purpose.

        :returns: an :py:class:`~nufhe.LweSampleArray` object
            with the result of the gate application.
    """

    def __init__(self, thread, cloud_key: NuFHECloudKey, perf_params: PerformanceParameters=None):
        "__init__()"
        if perf_params is None:
            perf_params = PerformanceParameters(cloud_key.params)

        perf_params = perf_params.for_device(thread.device_params)

        self.thread = thread
        self.params = cloud_key.params
        self.cloud_key = cloud_key
        self.perf_params = perf_params

    def empty_ciphertext(self, shape):
        """
        Returns an unitialized ciphertext (an :py:class:`~nufhe.LweSampleArray` object).

        The low-level analogue: :py:func:`empty_ciphertext`.
        """
        return empty_ciphertext(self.thread, self.params, shape)

    def load_ciphertext(self, file):
        """
        Load a ciphertext (a :py:class:`~nufhe.LweSampleArray` object) serialized with
        :py:meth:`LweSampleArray.dump <nufhe.LweSampleArray.dump>` into the context memory space.

        The low-level analogue: :py:meth:`LweSampleArray.load <nufhe.LweSampleArray.load>`.

        :returns: an :py:class:`~nufhe.LweSampleArray` object
        """
        return LweSampleArray.load(file, self.thread)

    def _gate(self, name, *args, dest: LweSampleArray=None):
        if dest is None:
            dest = self.empty_ciphertext(args[0].shape)
        gate_func = getattr(gates, name)
        gate_func(self.thread, self.cloud_key, dest, *args, perf_params=self.perf_params)
        return dest

    def __getattr__(self, name):
        if name.startswith('gate_'):
            return lambda *args, **kwds: self._gate(name, *args, **kwds)
        else:
            raise AttributeError(name)
