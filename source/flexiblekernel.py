'''
Created Nov 2012

@authors: James Robert Lloyd (jrl44@cam.ac.uk)
          David Duvenaud (dkd23@cam.ac.uk)
          Roger Grosse (rgrosse@mit.edu)
'''

import itertools
import numpy as np
try:
    import termcolor
    has_termcolor = True
except:
    has_termcolor = False

import config
from utils import psd_matrices
import utils.misc
import re

PAREN_COLORS = ['red', 'green', 'blue', 'cyan', 'magenta', 'yellow']
#### MAGIC NUMBER - CAUTION
CMP_TOLERANCE = np.log(1.01) # i.e. 1%

def shrink_below_tolerance(x):
    if np.abs(x) < CMP_TOLERANCE:
        return 0
    else:
        return x 

def paren_colors():
    if config.COLOR_SCHEME == 'dark':
        return ['red', 'green', 'cyan', 'magenta', 'yellow']
    elif config.COLOR_SCHEME == 'light':
        return ['blue', 'red', 'magenta', 'green', 'cyan']
    else:
        raise RuntimeError('Unknown color scheme: %s' % config.COLOR_SCHEME)

def colored(text, depth):
    if has_termcolor:
        colors = paren_colors()
        color = colors[depth % len(colors)]
        return termcolor.colored(text, color, attrs=['bold'])
    else:
        return text

class KernelFamily:
    pass

class Kernel:
    def __add__(self, other):
        assert isinstance(other, Kernel)
        if isinstance(other, SumKernel):
            return SumKernel([self] + other.operands).copy()
        else:
            return SumKernel([self, other]).copy()
    
    def __mul__(self, other):
        assert isinstance(other, Kernel)
        if isinstance(other, ProductKernel):
            return ProductKernel([self] + other.operands).copy()
        else:
            return ProductKernel([self, other])

class BaseKernelFamily(KernelFamily):
    pass

class BaseKernel(Kernel):
    def effective_params(self):
        '''This is true of all base kernels, hence definition here'''  
        return len(self.param_vector())
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Returns the parameter vector with any default values replaced with random Gaussian'''
        return [np.random.normal(scale=sd) if p == 0 else p for p in self.param_vector()]
        
    def out_of_bounds(self, constraints):
        '''Most kernels are allowed to have any parameter value'''
        return False

class SqExpKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return SqExpKernel(lengthscale=lengthscale, output_variance=output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('SqExp', self.depth())
    
    def default(self):
        return SqExpKernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'SE'
    
    @staticmethod    
    def description():
        return "Squared-exponential"

    @staticmethod    
    def params_description():
        return "lengthscale"    

class SqExpKernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.lengthscale = lengthscale
        self.output_variance = output_variance
        
    def family(self):
        return SqExpKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covSEiso}'
    
    def english_name(self):
        return 'SqExp'
    
    def id_name(self):
        return 'SE'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale or neutrally
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return SqExpKernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'SqExpKernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('SE(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'SE'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
    
    def depth(self):
        return 0
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale']


class SqExpPeriodicKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, period, output_variance = params
        return SqExpPeriodicKernel(lengthscale, period, output_variance)
    
    def num_params(self):
        return 3
    
    def pretty_print(self):
        return colored('PE', self.depth())
    
    # FIXME - Caution - magic numbers!
    def default(self):
        return SqExpPeriodicKernel(0., -2.0, 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Per'
    
    @staticmethod    
    def description():
        return "Periodic"

    @staticmethod    
    def params_description():
        return "lengthscale, period"  
    
class SqExpPeriodicKernel(BaseKernel):
    def __init__(self, lengthscale, period, output_variance):
        self.lengthscale = lengthscale
        self.period = period
        self.output_variance = output_variance
        
    def family(self):
        return SqExpPeriodicKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covPeriodic}'
    
    def english_name(self):
        return 'Periodic'
    
    def id_name(self):
        return 'Per'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.period, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Overwrites base method, using min period to prevent Nyquist errors'''
        result = self.param_vector()
        if result[0] == 0:
            # Min period represents a minimum sensible scale - use it for lengthscale as well
            # Scale with data_scale though
            if data_shape['min_period'] is None:
                result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
            else:
                result[0] = utils.misc.sample_truncated_normal(loc=data_shape['input_scale'], scale=sd, min_value=data_shape['min_period'])
        if result[1] == -2:
            #### FIXME - Caution, magic numbers
            # Min period represents a minimum sensible scale
            # Scale with data_scale
            if data_shape['min_period'] is None:
                result[1] = np.random.normal(loc=data_shape['input_scale']-2, scale=sd)
            else:
                result[1] = utils.misc.sample_truncated_normal(loc=data_shape['input_scale']-2, scale=sd, min_value=data_shape['min_period'])
        if result[2] == 0:
            # Set scale factor with output scale or neutrally
            if np.random.rand() < 0.5:
                result[2] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[2] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return SqExpPeriodicKernel(self.lengthscale, self.period, self.output_variance)
    
    def __repr__(self):
        return 'SqExpPeriodicKernel(lengthscale=%f, period=%f, output_variance=%f)' % \
            (self.lengthscale, self.period, self.output_variance)
    
    def pretty_print(self):
        return colored('PE(ell=%1.1f, p=%1.1f, sf=%1.1f)' % (self.lengthscale, self.period, self.output_variance),
                       self.depth())
        
    def latex_print(self):
        # return 'PE(\\ell=%1.1f, p=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.period, self.output_variance)
        #return 'PE(p=%1.1f)' % self.period          
        return 'Per'
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.period - other.period, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.period - other.period, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.period, self.output_variance), 
#                   (other.lengthscale, other.period, other.output_variance))
        
    def depth(self):
        return 0
            
    def out_of_bounds(self, constraints):
        return (self.period < constraints['min_period']) or (self.lengthscale < constraints['min_lengthscale']) or (self.period > np.log(0.5*(constraints['input_max'] - constraints['input_min'])))
        
class CosineKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        period, output_variance = params
        return CosineKernel(period, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('Cos', self.depth())
    
    # FIXME - Caution - magic numbers!
    def default(self):
        return CosineKernel(-2.0, 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Cos'
    
    @staticmethod    
    def description():
        return "Cosine"

    @staticmethod    
    def params_description():
        return "period"  
    
class CosineKernel(BaseKernel):
    def __init__(self, period, output_variance):
        self.period = period
        self.output_variance = output_variance
        
    def family(self):
        return CosineKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covCos}'
    
    def english_name(self):
        return 'Cosine'
    
    def id_name(self):
        return 'Cos'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.period, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Overwrites base method, using min period to prevent Nyquist errors'''
        result = self.param_vector()
        if result[0] == -2:
            #### FIXME - Caution, magic numbers
            # Min period represents a minimum sensible scale
            # Scale with data_scale
            if data_shape['min_period'] is None:
                result[0] = np.random.normal(loc=data_shape['input_scale']-2, scale=sd)
            else:
                result[0] = utils.misc.sample_truncated_normal(loc=data_shape['input_scale']-2, scale=sd, min_value=data_shape['min_period'])
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return CosineKernel(self.period, self.output_variance)
    
    def __repr__(self):
        return 'CosineKernel(period=%f, output_variance=%f)' % \
            (self.period, self.output_variance)
    
    def pretty_print(self):
        return colored('Cos(p=%1.1f, sf=%1.1f)' % (self.period, self.output_variance),
                       self.depth())
        
    def latex_print(self):
        # return 'PE(\\ell=%1.1f, p=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.period, self.output_variance)
        #return 'PE(p=%1.1f)' % self.period          
        return 'Cos'
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.period - other.period, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.period - other.period, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.period, self.output_variance), 
#                   (other.lengthscale, other.period, other.output_variance))
        
    def depth(self):
        return 0
            
    def out_of_bounds(self, constraints):
        return (self.period < constraints['min_period']) or (self.period > np.log(0.5*(constraints['input_max'] - constraints['input_min'])))
        
class SpectralKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance, period = params
        return SpectralKernel(lengthscale, period, output_variance)
    
    def num_params(self):
        return 3
    
    def pretty_print(self):
        return colored('SP', self.depth())
    
    # FIXME - Caution - magic numbers!
    def default(self):
        return SpectralKernel(0., -2.0, 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'SP'
    
    @staticmethod    
    def description():
        return "Spectral"

    @staticmethod    
    def params_description():
        return "lengthscale, period"  
    
class SpectralKernel(BaseKernel):
    def __init__(self, lengthscale, period, output_variance):
        self.lengthscale = lengthscale
        self.period = period
        self.output_variance = output_variance
        
    def family(self):
        return SpectralKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covProd, {@covSEiso, @covCosUnit}}'
    
    def english_name(self):
        return 'Spectral'
    
    def id_name(self):
        return 'SP'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance, self.period])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Overwrites base method, using min period to prevent Nyquist errors'''
        result = self.param_vector()
        if result[0] == 0:
            # Min period represents a minimum sensible scale - use it for lengthscale as well
            # Scale with data_scale though
            if data_shape['min_period'] is None:
                result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
            else:
                result[0] = utils.misc.sample_truncated_normal(loc=data_shape['input_scale'], scale=sd, min_value=data_shape['min_period'])
        if result[2] == -2:
            #### FIXME - Caution, magic numbers
            # Min period represents a minimum sensible scale
            # Scale with data_scale
            if data_shape['min_period'] is None:
                result[2] = np.random.normal(loc=data_shape['input_scale']-2, scale=sd)
            else:
                result[2] = utils.misc.sample_truncated_normal(loc=data_shape['input_scale']-2, scale=sd, min_value=data_shape['min_period'])
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return SpectralKernel(self.lengthscale, self.period, self.output_variance)
    
    def __repr__(self):
        return 'SpectralKernel(lengthscale=%f, period=%f, output_variance=%f)' % \
            (self.lengthscale, self.period, self.output_variance)
    
    def pretty_print(self):
        return colored('SP(ell=%1.1f, p=%1.1f, sf=%1.1f)' % (self.lengthscale, self.period, self.output_variance),
                       self.depth())
        
    def latex_print(self):
        # return 'PE(\\ell=%1.1f, p=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.period, self.output_variance)
        #return 'PE(p=%1.1f)' % self.period          
        return 'Spec'
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.period - other.period, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.period - other.period, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.period, self.output_variance), 
#                   (other.lengthscale, other.period, other.output_variance))
        
    def depth(self):
        return 0
            
    def out_of_bounds(self, constraints):
        return (self.period < constraints['min_period']) or (self.lengthscale < constraints['min_lengthscale']) or (self.period > np.log(0.5*(constraints['input_max'] - constraints['input_min'])))

class RQKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance, alpha = params
        return RQKernel(lengthscale, output_variance, alpha)
    
    def num_params(self):
        return 3
    
    def pretty_print(self):
        return colored('RQ', self.depth())
    
    def default(self):
        return RQKernel(0., 0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'RQ'
    
    @staticmethod    
    def description():
        return "Rational Quadratic"

    @staticmethod    
    def params_description():
        return "lengthscale, alpha"
        
    
class RQKernel(BaseKernel):
    def __init__(self, lengthscale, output_variance, alpha):
        self.lengthscale = lengthscale
        self.output_variance = output_variance
        self.alpha = alpha
        
    def family(self):
        return RQKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covRQiso}'
    
    def english_name(self):
        return 'RQ'
    
    def id_name(self):
        return 'RQ'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance, self.alpha])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        if result[2] == 0:
            # Set alpha indepedently of data shape
            result[2] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return RQKernel(self.lengthscale, self.output_variance, self.alpha)
    
    def __repr__(self):
        return 'RQKernel(lengthscale=%f, output_variance=%f, alpha=%f)' % \
            (self.lengthscale, self.output_variance, self.alpha)
    
    def pretty_print(self):
        return colored('RQ(ell=%1.1f, sf=%1.1f, a=%1.1f)' % (self.lengthscale, self.output_variance, self.alpha),
                       self.depth())
        
    def latex_print(self):
        #return 'RQ(\\ell=%1.1f, \\alpha=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.alpha, self.output_variance)
        #return 'RQ(\\ell=%1.1f)' % self.lengthscale
        return 'RQ'           
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance, self.alpha - other.alpha]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance, self.alpha - other.alpha]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0   
            
    def out_of_bounds(self, constraints):
        return (self.lengthscale < constraints['min_lengthscale']) or (self.alpha < constraints['min_alpha'])
    
class ConstKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        #### Note - expects list input
        output_variance, = params
        return ConstKernel(output_variance)
    
    def num_params(self):
        return 1
    
    def pretty_print(self):
        return colored('CS', self.depth())
    
    def default(self):
        return ConstKernel(0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Const'
    
    @staticmethod    
    def description():
        return "Constant"

    @staticmethod    
    def params_description():
        return "Output variance"        
    
class ConstKernel(BaseKernel):
    def __init__(self, output_variance):
        self.output_variance = output_variance
        
    def family(self):
        return ConstKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covConst}'
    
    def english_name(self):
        return 'CS'
    
    def id_name(self):
        return 'Const'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.output_variance])

    def copy(self):
        return ConstKernel(self.output_variance)
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set scale factor with output scale
            result[0] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
        return result
    
    def __repr__(self):
        return 'ConstKernel(output_variance=%f)' % \
            (self.output_variance)
    
    def pretty_print(self):
        return colored('CS(sf=%1.1f)' % (self.output_variance),
                       self.depth())
        
    def latex_print(self):
        return 'CS'    
    
    def id_name(self):
        return 'Const'       
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0    
        
class ZeroKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        #### Note - expects list input
        assert params == []
        return ZeroKernel()
    
    def num_params(self):
        return 0
    
    def pretty_print(self):
        return colored('NIL', self.depth())
    
    def default(self):
        return ZeroKernel()
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Zero'
    
    @staticmethod    
    def description():
        return "Zero"

    @staticmethod    
    def params_description():
        return "None"        
    
class ZeroKernel(BaseKernel):
    def __init__(self):
        pass
        
    def family(self):
        return ZeroKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covZero}'
    
    def english_name(self):
        return 'NIL'
    
    def id_name(self):
        return 'Zero'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([])

    def copy(self):
        return ZeroKernel()
        
    def default_params_replaced(self, sd=1, data_shape=None):
        return self.param_vector()
    
    def __repr__(self):
        return 'ZeroKernel()'
    
    def pretty_print(self):
        return colored('NIL', self.depth())
        
    def latex_print(self):
        return 'NIL'       
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        return cmp(self.__class__, other.__class__)
        
    def depth(self):
        return 0   

class LinKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        offset, lengthscale, location = params
        return LinKernel(offset=offset, lengthscale=lengthscale, location=location)
    
    def num_params(self):
        return 3
    
    def pretty_print(self):
        return colored('LN', self.depth())
    
    def default(self):
        return LinKernel(-0., 0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Lin'

    @staticmethod    
    def description():
        return "Linear"

    @staticmethod    
    def params_description():
        return "bias"
    
class LinKernel(BaseKernel):
    # FIXME - lengthscale is actually an inverse scale
    def __init__(self, offset=0, lengthscale=0, location=0):
        self.offset = offset
        self.lengthscale = lengthscale
        self.location = location
        
    def family(self):
        return LinKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covSum, {@covConst, @covLINscaleshift}}'
    
    def english_name(self):
        return 'LN'
    
    def id_name(self):
        return 'Lin'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.offset, self.lengthscale, self.location])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[0] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[0] = np.random.normal(loc=0, scale=sd)
        if result[1] == 0:
            # Lengthscale scales inverselywith ratio of y std and x std (gradient = delta y / delta x)
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=-(data_shape['output_scale'] - data_shape['input_scale']), scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        if result[2] == 0:
            # Location moves with input location, and variance scales in input variance
            #### TODO - this should probably be closer to uniform (but allowed to bleed beyond edges)
            result[2] = np.random.normal(loc=data_shape['input_location'], scale=0.5*sd*np.exp(data_shape['input_scale']))
        return result
        
    def effective_params(self):
        '''It's linear regression'''  
        return 2

    def copy(self):
        return LinKernel(offset=self.offset, lengthscale=self.lengthscale, location=self.location)
    
    def __repr__(self):
        return 'LinKernel(offset=%f, lengthscale=%f, location=%f)' % \
            (self.offset, self.lengthscale, self.location)
    
    def pretty_print(self):
        return colored('LN(off=%1.1f, ell=%1.1f, loc=%1.1f)' % (self.offset, self.lengthscale, self.location),
                       self.depth())
        
    def latex_print(self):
        return 'Lin'           
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.offset - other.offset, self.lengthscale - other.lengthscale, self.location - other.location]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0 
        
class StepKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        location, steepness, sf1, sf2 = params
        return StepKernel(location=location, steepness=steepness, sf1=sf1, sf2=sf2)
    
    def num_params(self):
        return 4
    
    def pretty_print(self):
        return colored('ST', self.depth())
    
    def default(self):
        return StepKernel(0., 0., 0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Step'

    @staticmethod    
    def description():
        return "Step"

    @staticmethod    
    def params_description():
        return "location, steepness, sf1, sf2"
    
class StepKernel(BaseKernel):
    def __init__(self, location=0, steepness=0, sf1=0, sf2=0):
        self.location = location
        self.steepness = steepness
        self.sf1 = sf1
        self.sf2 = sf2
        
    def family(self):
        return StepKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covChangePoint, {@covConst, @covConst}}'
    
    def english_name(self):
        return 'Step'
    
    def id_name(self):
        return 'Step'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.location, self.steepness, self.sf1, self.sf2])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Location moves with input location, and variance scales in input variance
            result[0] = np.random.normal(loc=data_shape['input_location'], scale=0.5*sd*np.exp(data_shape['input_scale']))
        if result[1] == 0:
            # Set steepness with inverse input scale
            #### TODO - Check me more thoroughly
            result[1] = np.random.normal(loc=4-np.log((data_shape['input_max'] - data_shape['input_min'])), scale=0.5*sd)
        if result[2] == 0:
            # Set scale factor with output scale
            result[2] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
        if result[3] == 0:
            # Set scale factor with output scale
            result[3] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
        return result
        
    def effective_params(self):
        return 4

    def copy(self):
        return StepKernel(location=self.location, steepness=self.steepness, sf1=self.sf1, sf2=self.sf2)
    
    def __repr__(self):
        return 'StepKernel(location=%f, steepness=%f, sf1=%f, sf2=%f)' % \
            (self.location, self.steepness, self.sf1, self.sf2)
    
    def pretty_print(self):
        return colored('ST(loc=%1.1f, steep=%1.1f, sf1=%1.1f, sf2=%1.1f)' % (self.location, self.steepness, self.sf1, self.sf2),
                       self.depth())
        
    def latex_print(self):
        return 'Step'           
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.location - other.location, self.steepness - other.steepness, self.sf1 - other.sf1, self.sf2 - other.sf2]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0 
            
    def out_of_bounds(self, constraints): #### TODO - check me!
        return (self.location < constraints['input_min'] + 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.location > constraints['input_max'] - 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.steepness < -np.log((constraints['input_max'] -constraints['input_min'])) + 3)
        
class IBMKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        rate, location = params
        return IBMKernel(rate=rate, location=location)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('IBM', self.depth())
    
    def default(self):
        return IBMKernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'IBM'

    @staticmethod    
    def description():
        return "Integrated Brownian Motion"

    @staticmethod    
    def params_description():
        return "rate, location"
    
class IBMKernel(BaseKernel):
    def __init__(self, rate=0, location=0):
        self.rate = rate
        self.location = location
        
    def family(self):
        return IBMKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covIBM}'
    
    def english_name(self):
        return 'IBM'
    
    def id_name(self):
        return 'IBM'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.rate, self.location])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            #### TODO - any idea how to initialise the rate parameter?
            result[0] = np.random.normal(loc=0, scale=sd)
        if result[1] == 0:
            # Location moves with input location, and variance scales in input variance
            result[1] = np.random.normal(loc=data_shape['input_location'], scale=sd*np.exp(data_shape['input_scale']))
        return result
        
    def effective_params(self):  
        return 2

    def copy(self):
        return IBMKernel(rate=self.rate, location=self.location)
    
    def __repr__(self):
        return 'IBMKernel(rate=%f, location=%f)' % \
            (self.rate, self.location)
    
    def pretty_print(self):
        return colored('IBM(rate=%1.1f, loc=%1.1f)' % (self.rate, self.location),
                       self.depth())
        
    def latex_print(self):
        return 'IBM'           
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.rate - other.rate, self.location - other.location]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0 
        
class IBMLinKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        rate, location, offset, scale = params
        return IBMLinKernel(rate=rate, location=location, offset=offset, scale=scale)
    
    def num_params(self):
        return 4
    
    def pretty_print(self):
        return colored('IBMLin', self.depth())
    
    def default(self):
        return IBMLinKernel(0., 0., 0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'IBMLin'

    @staticmethod    
    def description():
        return "Integrated Brownian Motion + Linear"

    @staticmethod    
    def params_description():
        return "rate, location, offset, scale"
    
class IBMLinKernel(BaseKernel):
    def __init__(self, rate=0, location=0, offset=0, scale=0):
        self.rate = rate
        self.location = location
        self.offset = offset
        self.scale = scale
        
    def family(self):
        return IBMLinKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covIBMLin}'
    
    def english_name(self):
        return 'IBMLin'
    
    def id_name(self):
        return 'IBMLin'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.rate, self.location, self.offset, self.scale])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            result[0] = np.random.normal(loc=0, scale=sd)
        if result[1] == 0:
            # Location moves with input location, and variance scales in input variance
            result[1] = np.random.normal(loc=data_shape['input_location'], scale=sd*np.exp(data_shape['input_scale']))
        if result[2] == 0:
            result[2] = np.random.normal(loc=0, scale=sd)
        if result[3] == 0:
            # Lengthscale scales with ratio of y std and x std (gradient = delta y / delta x)
            if np.random.rand() < 0.5:
                result[3] = np.random.normal(loc=data_shape['output_scale'] - data_shape['input_scale'], scale=sd)
            else:
                result[3] = np.random.normal(loc=0, scale=sd)
        return result
        
    def effective_params(self):  
        #### FIXME - is this sensible?
        return 3

    def copy(self):
        return IBMLinKernel(rate=self.rate, location=self.location, offset=self.offset, scale=self.scale)
    
    def __repr__(self):
        return 'IBMLinKernel(rate=%f, location=%f, offset=%f, scale=%f)' % \
            (self.rate, self.location, self.offset, self.scale)
    
    def pretty_print(self):
        return colored('IBMLin(rate=%1.1f, loc=%1.1f, off=%1.1f, scale=%1.1f)' % (self.rate, self.location, self.offset, self.scale),
                       self.depth())
        
    def latex_print(self):
        return 'IBMLin'           
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.rate - other.rate, self.location - other.location, self.offset - other.offset, self.scale - other.scale]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0 

class QuadraticKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        offset, output_variance = params
        return QuadraticKernel(offset, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('QD', self.depth())
    
    def default(self):
        return QuadraticKernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Quad'
    
    @staticmethod    
    def description():
        return "Quadratic"

    @staticmethod    
    def params_description():
        return "offset"     
    
class QuadraticKernel(BaseKernel):
    def __init__(self, offset, output_variance):
        #### FIXME - Should the offset defauly to something small? Or will we never use this kernel
        #### If using this kernel we should also add the default params replaced function
        self.offset = offset
        self.output_variance = output_variance
        
    def family(self):
        return QuadraticKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covPoly, 2}'
    
    def english_name(self):
        return 'QD'
    
    def id_name(self):
        return 'Quad'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.offset, self.output_variance])

    def copy(self):
        return QuadraticKernel(self.offset, self.output_variance)
    
    def __repr__(self):
        return 'QuadraticKernel(offset=%f, output_variance=%f)' % \
            (self.offset, self.output_variance)
    
    def pretty_print(self):
        return colored('QD(off=%1.1f, sf=%1.1f)' % (self.offset, self.output_variance),
                       self.depth())
        
    def latex_print(self):
        return 'QD'           
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.offset - other.offset, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.offset - other.offset, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0   

class CubicKernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        offset, output_variance = params
        return CubicKernel(offset, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('CB', self.depth())
    
    def default(self):
        return CubicKernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'Cubic'
    
    @staticmethod    
    def description():
        return "Cubic"

    @staticmethod    
    def params_description():
        return "offset"     
    
class CubicKernel(BaseKernel):
    def __init__(self, offset, output_variance):
        #### FIXME - Should the offset defauly to something small? Or will we never use this kernel
        #### If using this kernel we should also add the default params replaced function
        self.offset = offset
        self.output_variance = output_variance
        
    def family(self):
        return CubicKernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covPoly, 3}'
    
    def english_name(self):
        return 'CB'
    
    def id_name(self):
        return 'Cubic'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.offset, self.output_variance])

    def copy(self):
        return CubicKernel(self.offset, self.output_variance)
    
    def __repr__(self):
        return 'CubicKernel(offset=%f, output_variance=%f)' % \
            (self.offset, self.output_variance)
    
    def pretty_print(self):
        return colored('CB(off=%1.1f, sf=%1.1f)' % (self.offset, self.output_variance),
                       self.depth())
        
    def latex_print(self):
        return 'CB'           
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.offset - other.offset, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.offset - other.offset, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance, self.alpha), 
#                   (other.lengthscale, other.output_variance, other.alpha))
        
    def depth(self):
        return 0   

class PP0KernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return PP0Kernel(lengthscale, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('P0', self.depth())
    
    def default(self):
        return PP0Kernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'PP0'

    @staticmethod    
    def description():
        return "Piecewise Polynomial 0"

    @staticmethod    
    def params_description():
        return "lengthscale"   
    

class PP0Kernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.output_variance = output_variance
        self.lengthscale = lengthscale
        
    def family(self):
        return PP0KernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covPPiso, 0}'
    
    def english_name(self):
        return 'P0'
    
    def id_name(self):
        return 'PP0'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return PP0Kernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'PP0Kernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('P0(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'P0'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance), (other.lengthscale, other.output_variance))
    
    def depth(self):
        return 0 
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale']
      

class PP1KernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return PP1Kernel(lengthscale, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('P1', self.depth())
    
    def default(self):
        return PP1Kernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'PP1'
    
    @staticmethod    
    def description():
        return "Piecewise Polynomial 1"

    @staticmethod    
    def params_description():
        return "lengthscale"      

class PP1Kernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.output_variance = output_variance
        self.lengthscale = lengthscale
        
    def family(self):
        return PP1KernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covPPiso, 1}'
    
    def english_name(self):
        return 'P1'
    
    def id_name(self):
        return 'PP1'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return PP1Kernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'PP1Kernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('P1(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'P1'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance), (other.lengthscale, other.output_variance))
    
    def depth(self):
        return 0 
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale']
        

class PP2KernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return PP2Kernel(lengthscale, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('P2', self.depth())
    
    def default(self):
        return PP2Kernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'PP2'
    
    @staticmethod    
    def description():
        return "Piecewise Polynomial 2"

    @staticmethod    
    def params_description():
        return "lengthscale"      

class PP2Kernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.output_variance = output_variance
        self.lengthscale = lengthscale
        
    def family(self):
        return PP2KernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covPPiso, 2}'
    
    def english_name(self):
        return 'P2'
    
    def id_name(self):
        return 'PP2'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return PP2Kernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'PP2Kernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('P2(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'P2'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance), (other.lengthscale, other.output_variance))
    
    def depth(self):
        return 0
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale']


class PP3KernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return PP3Kernel(lengthscale, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('P3', self.depth())
    
    def default(self):
        return PP3Kernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'PP3'
    
    @staticmethod    
    def description():
        return "Piecewise Polynomial 3"

    @staticmethod    
    def params_description():
        return "lengthscale"       

class PP3Kernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.output_variance = output_variance
        self.lengthscale = lengthscale
        
    def family(self):
        return PP3KernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covPPiso, 3}'
    
    def english_name(self):
        return 'P3'
    
    def id_name(self):
        return 'PP3'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return PP3Kernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'PP3Kernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('P3(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'P3'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance), (other.lengthscale, other.output_variance))
    
    def depth(self):
        return 0 
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale']

class Matern1KernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return Matern1Kernel(lengthscale, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('MT1', self.depth())
    
    def default(self):
        return Matern1Kernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'MT1'
    
    @staticmethod    
    def description():
        return "Mat\\'{e}rn 1"

    @staticmethod    
    def params_description():
        return "lengthscale"    

class Matern1Kernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.lengthscale = lengthscale
        self.output_variance = output_variance
        
    def family(self):
        return Matern1KernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covMaterniso, 1}' # nu = 0.5
    
    def english_name(self):
        return 'MT1'
    
    def id_name(self):
        return 'MT1'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return Matern1Kernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'Matern1Kernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('MT1(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'MT1'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance), (other.lengthscale, other.output_variance))
    
    def depth(self):
        return 0 
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale']
        
class Matern3KernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return Matern3Kernel(lengthscale, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('MT3', self.depth())
    
    def default(self):
        return Matern3Kernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'MT3'
    
    @staticmethod    
    def description():
        return "Mat\\'{e}rn 3"

    @staticmethod    
    def params_description():
        return "lengthscale"    

class Matern3Kernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.lengthscale = lengthscale
        self.output_variance = output_variance
        
    def family(self):
        return Matern3KernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covMaterniso, 3}' # nu = 1.5
    
    def english_name(self):
        return 'MT3'
    
    def id_name(self):
        return 'MT3'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return Matern3Kernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'Matern3Kernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('MT3(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'MT3'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance), (other.lengthscale, other.output_variance))
    
    def depth(self):
        return 0 
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale'] 
        
class Matern5KernelFamily(BaseKernelFamily):
    def from_param_vector(self, params):
        lengthscale, output_variance = params
        return Matern5Kernel(lengthscale, output_variance)
    
    def num_params(self):
        return 2
    
    def pretty_print(self):
        return colored('MT5', self.depth())
    
    def default(self):
        return Matern5Kernel(0., 0.)
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return 0
    
    def depth(self):
        return 0
    
    def id_name(self):
        return 'MT5'
    
    @staticmethod    
    def description():
        return "Mat\\'{e}rn 5"

    @staticmethod    
    def params_description():
        return "lengthscale"    

class Matern5Kernel(BaseKernel):
    def __init__(self, lengthscale, output_variance):
        self.lengthscale = lengthscale
        self.output_variance = output_variance
        
    def family(self):
        return Matern5KernelFamily()
        
    def gpml_kernel_expression(self):
        return '{@covMaterniso, 5}' # nu = 2.5
    
    def english_name(self):
        return 'MT5'
    
    def id_name(self):
        return 'MT5'
    
    def param_vector(self):
        # order of args matches GPML
        return np.array([self.lengthscale, self.output_variance])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        result = self.param_vector()
        if result[0] == 0:
            # Set lengthscale with input scale
            result[0] = np.random.normal(loc=data_shape['input_scale'], scale=sd)
        if result[1] == 0:
            # Set scale factor with output scale
            if np.random.rand() < 0.5:
                result[1] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
            else:
                result[1] = np.random.normal(loc=0, scale=sd)
        return result

    def copy(self):
        return Matern5Kernel(self.lengthscale, self.output_variance)
    
    def __repr__(self):
        return 'Matern5Kernel(lengthscale=%f, output_variance=%f)' % (self.lengthscale, self.output_variance)
    
    def pretty_print(self):
        return colored('MT5(ell=%1.1f, sf=%1.1f)' % (self.lengthscale, self.output_variance), self.depth())
    
    def latex_print(self):
        #return 'SE(\\ell=%1.1f, \\sigma=%1.1f)' % (self.lengthscale, self.output_variance)    
        #return 'SE(\\ell=%1.1f)' % self.lengthscale
        return 'MT5'
        
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        differences = [self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]
        differences = map(shrink_below_tolerance, differences)
        return cmp(differences, [0] * len(differences))
#        max_diff = max(np.abs([self.lengthscale - other.lengthscale, self.output_variance - other.output_variance]))
#        return max_diff > CMP_TOLERANCE
#        return cmp((self.lengthscale, self.output_variance), (other.lengthscale, other.output_variance))
    
    def depth(self):
        return 0 
            
    def out_of_bounds(self, constraints):
        return self.lengthscale < constraints['min_lengthscale']    
        
class MaskKernelFamily(KernelFamily):
    def __init__(self, ndim, active_dimension, base_kernel_family):
        assert 0 <= active_dimension < ndim
        self.ndim = ndim
        self.active_dimension = active_dimension    # first dimension is 0
        self.base_kernel_family = base_kernel_family
        
    def from_param_vector(self, params):
        return MaskKernel(self.ndim, self.active_dimension, self.base_kernel_family.from_param_vector(params))
    
    def num_params(self):
        return self.base_kernel_family.num_params()
    
    def pretty_print(self):
        #return colored('Mask(%d, ' % self.active_dimension, self.depth()) + \
        return colored('M(%d, ' % self.active_dimension, self.depth()) + \
            self.base_kernel_family.pretty_print() + \
            colored(')', self.depth())
    
    def default(self):
        return MaskKernel(self.ndim, self.active_dimension, self.base_kernel_family.default())
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp((self.ndim, self.active_dimension, self.base_kernel_family),
                   (other.ndim, other.active_dimension, other.base_kernel_family))
        
    def depth(self):
        return self.base_kernel_family.depth() + 1
    
    
class MaskKernel(Kernel):
    def __init__(self, ndim, active_dimension, base_kernel):
        assert 0 <= active_dimension < ndim
        self.ndim = ndim
        self.active_dimension = active_dimension    # first dimension is 0
        self.base_kernel = base_kernel
        
    def copy(self):
        return MaskKernel(self.ndim, self.active_dimension, self.base_kernel.copy())
        
    def family(self):
        return MaskKernelFamily(self.ndim, self.active_dimension, self.base_kernel.family())
        
    def gpml_kernel_expression(self):
        dim_vec = np.zeros(self.ndim, dtype=int)
        dim_vec[self.active_dimension] = 1
        dim_vec_str = '[' + ' '.join(map(str, dim_vec)) + ']'
        return '{@covMask, {%s, %s}}' % (dim_vec_str, self.base_kernel.gpml_kernel_expression())
    
    def pretty_print(self):
        return colored('M(%d, ' % self.active_dimension, self.depth()) + \
            self.base_kernel.pretty_print() + \
            colored(')', self.depth())
            
    def latex_print(self):
        #return 'M_%d \\left(' % self.active_dimension + self.base_kernel.latex_print() + '\\right)'                 
        return self.base_kernel.latex_print() + '_{%d}' % self.active_dimension
            
    def __repr__(self):
        return 'MaskKernel(ndim=%d, active_dimension=%d, base_kernel=%s)' % \
            (self.ndim, self.active_dimension, self.base_kernel.__repr__())            
    
    def param_vector(self):
        return self.base_kernel.param_vector()
        
    def effective_params(self):
        return self.base_kernel.effective_params()
        
    def default_params_replaced(self, sd=1, data_shape=None):
        # Replaces multi-d parameters with appropriate dimensions selected
        # If parameters are already 1-d then it does nothing
        if isinstance(data_shape['input_location'], (list, tuple, np.ndarray)):
            data_shape['input_location'] = data_shape['input_location'][self.active_dimension]
        if isinstance(data_shape['input_scale'], (list, tuple, np.ndarray)):
            data_shape['input_scale'] = data_shape['input_scale'][self.active_dimension]
        if isinstance(data_shape['min_period'], (list, tuple, np.ndarray)):
            data_shape['min_period'] = data_shape['min_period'][self.active_dimension]
        if isinstance(data_shape['input_min'], (list, tuple, np.ndarray)):
            data_shape['input_min'] = data_shape['input_min'][self.active_dimension]
        if isinstance(data_shape['input_max'], (list, tuple, np.ndarray)):
            data_shape['input_max'] = data_shape['input_max'][self.active_dimension]
        return self.base_kernel.default_params_replaced(sd=sd, data_shape=data_shape)
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp((self.ndim, self.active_dimension, self.base_kernel),
                   (other.ndim, other.active_dimension, other.base_kernel))
        
    def depth(self):
        return self.base_kernel.depth() + 1
            
    def out_of_bounds(self, constraints):
        # Extract relevant constraints
        if isinstance(constraints['min_period'], (list, tuple, np.ndarray)):
            # Pick out relevant minimum period
            constraints['min_period'] = constraints['min_period'][self.active_dimension]
        else:
            # min_period either one dimensional or None - do nothing
            pass
        if isinstance(constraints['input_min'], (list, tuple, np.ndarray)):
            constraints['input_min'] = constraints['input_min'][self.active_dimension]
        if isinstance(constraints['input_max'], (list, tuple, np.ndarray)):
            constraints['input_max'] = constraints['input_max'][self.active_dimension]
        return self.base_kernel.out_of_bounds(constraints)
    

class ChangePointKernelFamily(KernelFamily):
    def __init__(self, operands):
        self.operands = operands
        assert len(operands) == 2
        
    def from_param_vector(self, params):
        location = params[0]
        steepness = params[1]
        start = 2
        ops = []
        for e in self.operands:
            end = start + e.num_params()
            ops.append(e.from_param_vector(params[start:end]))
            start = end
        return ChangePointKernel(location, steepness, ops)
    
    def num_params(self):
        return 2 + sum([e.num_params() for e in self.operands])
    
    def pretty_print(self):        
        return colored('CP(', self.depth()) + \
            self.operands[0].pretty_print() + \
            colored(', ', self.depth()) + \
            self.operands[1].pretty_print() + \
            colored(')', self.depth())
    
    def default(self):
        return ChangePointKernel(0., 0., [op.default() for op in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp(self.operands, other.operands)
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1

class ChangePointKernel(Kernel):
    def __init__(self, location, steepness, operands):
        self.location = location
        self.steepness = steepness
        self.operands = operands
        
    def family(self):
        return ChangePointKernelFamily([e.family() for e in self.operands])
        
    def pretty_print(self): 
        return colored('CP(loc=%1.1f, steep=%1.1f, ' % (self.location, self.steepness), self.depth()) + \
            self.operands[0].pretty_print() + \
            colored(', ', self.depth()) + \
            self.operands[1].pretty_print() + \
            colored(')', self.depth())
            
    def latex_print(self):
        return 'CP\\left( ' + ' , '.join([e.latex_print() for e in self.operands]) + ' \\right)'            
            
    def __repr__(self):
        return 'ChangePointKernel(location=%f, steepness=%f, operands=%s)' % \
            (self.location, self.steepness, '[ ' + ', '.join([o.__repr__() for o in self.operands]) + ' ]')                
    
    def gpml_kernel_expression(self):
        return '{@covChangePoint, {%s}}' % ', '.join(e.gpml_kernel_expression() for e in self.operands)
    
    def copy(self):
        return ChangePointKernel(self.location, self.steepness, [e.copy() for e in self.operands])

    def param_vector(self):
        return np.concatenate([np.array([self.location, self.steepness])] + [e.param_vector() for e in self.operands])
        
    def effective_params(self):
        return 2 + sum([o.effective_params() for o in self.operands])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Returns the parameter vector with any default values replaced with random Gaussian'''
        result = self.param_vector()[:2]
        if result[0] == 0: #### TODO - Make sure this default matches that in self.default() - should do when on log scale
            # Location moves with input location, and variance scales in input variance
            # Expect change points to occur with the data
            #### TODO - check us for sensibleness!
            result[0] = np.random.normal(loc=data_shape['input_location'], scale=0.5*sd*np.exp(data_shape['input_scale']))
        if result[1] == 0:
            # Set steepness with inverse input scale
            #### TODO - is this correct scaling?
            result[1] = np.random.normal(loc=4-np.log((data_shape['input_max'] - data_shape['input_min'])), scale=0.5*sd)
        return np.concatenate([result] + [o.default_params_replaced(sd=sd, data_shape=data_shape) for o in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp((self.location, self.steepness, self.operands),
                   (other.location, other.steepness, other.operands))
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1
            
    def out_of_bounds(self, constraints): #### TODO - check me!
        return (self.location < constraints['input_min'] + 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.location > constraints['input_max'] - 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.steepness < -np.log((constraints['input_max'] -constraints['input_min'])) + 3) or \
               (any([o.out_of_bounds(constraints) for o in self.operands])) 
        
class BurstSEKernelFamily(KernelFamily):
    def __init__(self):
        pass
    
    def default(self):
        return BurstKernel(0., 0., 0., [SqExpKernelFamily().default()])
        
    def id_name(self):
        return 'BurstSE'
        
class BurstKernelFamily(KernelFamily):
    def __init__(self, operands):
        self.operands = operands
        assert len(operands) == 1
        
    def from_param_vector(self, params):
        location = params[0]
        steepness = params[1]
        width = params[2]
        start = 3
        ops = []
        for e in self.operands:
            end = start + e.num_params()
            ops.append(e.from_param_vector(params[start:end]))
            start = end
        return BurstKernel(location, steepness, width, ops)
    
    def num_params(self):
        return 3 + sum([e.num_params() for e in self.operands])
    
    def pretty_print(self):        
        return colored('B(', self.depth()) + \
            self.operands[0].pretty_print() + \
            colored(')', self.depth())
    
    def default(self):
        return BurstKernel(0., 0., 0., [op.default() for op in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp(self.operands, other.operands)
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1

class BurstKernel(Kernel):
    def __init__(self, location, steepness, width, operands):
        self.location = location
        self.steepness = steepness
        self.width = width
        self.operands = operands
        
    def family(self):
        return BurstKernelFamily([e.family() for e in self.operands])
        
    def pretty_print(self): 
        return colored('B(loc=%1.1f, steep=%1.1f, width=%1.1f, ' % (self.location, self.steepness, self.width), self.depth()) + \
            self.operands[0].pretty_print() + \
            colored(')', self.depth())
            
    def latex_print(self):
        return 'B\\left( ' + ' , '.join([e.latex_print() for e in self.operands]) + ' \\right)'            
            
    def __repr__(self):
        return 'BurstKernel(location=%f, steepness=%f, width=%f, operands=%s)' % \
            (self.location, self.steepness, self.width, '[ ' + ', '.join([o.__repr__() for o in self.operands]) + ' ]')                
    
    def gpml_kernel_expression(self):
        return '{@covBurst, {%s}}' % ', '.join(e.gpml_kernel_expression() for e in self.operands)
    
    def copy(self):
        return BurstKernel(self.location, self.steepness, self.width, [e.copy() for e in self.operands])

    def param_vector(self):
        return np.concatenate([np.array([self.location, self.steepness, self.width])] + [e.param_vector() for e in self.operands])
        
    def effective_params(self):
        return 3 + sum([o.effective_params() for o in self.operands])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Returns the parameter vector with any default values replaced with random Gaussian'''
        result = self.param_vector()[:3]
        if result[0] == 0: #### TODO - Make sure this default matches that in self.default() - should do when on log scale
            # Location moves with input location, and variance scales in input variance
            # Expect change points to occur with the data
            #### TODO - check us for sensibleness!
            result[0] = np.random.normal(loc=data_shape['input_location'], scale=0.5*sd*np.exp(data_shape['input_scale']))
        if result[1] == 0:
            # Set steepness with inverse input scale
            #### TODO - is this correct scaling?
            result[1] = np.random.normal(loc=4-np.log((data_shape['input_max'] - data_shape['input_min'])), scale=0.5*sd)
        if result[2] == 0:
            # Set width with input scale
            #### TODO - is this correct scaling?
            result[2] = np.random.normal(loc=np.log(0.1)+data_shape['input_scale'], scale=0.5*sd)
        return np.concatenate([result] + [o.default_params_replaced(sd=sd, data_shape=data_shape) for o in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp((self.location, self.steepness, self.width, self.operands),
                   (other.location, other.steepness, other.width, other.operands))
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1
            
    def out_of_bounds(self, constraints):#### TODO - check me!
        return (self.location < constraints['input_min'] + 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.location > constraints['input_max'] - 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.width > np.log(0.25*(constraints['input_max'] -constraints['input_min']))) or \
               (self.steepness < -np.log((constraints['input_max'] -constraints['input_min'])) + 3) or \
               (any([o.out_of_bounds(constraints) for o in self.operands])) 
               
class BlackoutKernelFamily(KernelFamily):
    def __init__(self, operands):
        self.operands = operands
        assert len(operands) == 1
        
    def from_param_vector(self, params):
        location = params[0]
        steepness = params[1]
        width = params[2]
        sf = params[3]
        start = 4
        ops = []
        for e in self.operands:
            end = start + e.num_params()
            ops.append(e.from_param_vector(params[start:end]))
            start = end
        return BlackoutKernel(location, steepness, width, sf, ops)
    
    def num_params(self):
        return 4 + sum([e.num_params() for e in self.operands])
    
    def pretty_print(self):        
        return colored('BL(', self.depth()) + \
            self.operands[0].pretty_print() + \
            colored(')', self.depth())
    
    def default(self):
        return BurstKernel(0., 0., 0., 0., [op.default() for op in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp(self.operands, other.operands)
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1

class BurstKernel(Kernel):
    def __init__(self, location, steepness, width, sf, operands):
        self.location = location
        self.steepness = steepness
        self.width = width
        self.sf = sf
        self.operands = operands
        
    def family(self):
        return BlackoutKernelFamily([e.family() for e in self.operands])
        
    def pretty_print(self): 
        return colored('BL(loc=%1.1f, steep=%1.1f, width=%1.1f, sf=%1.1f, ' % (self.location, self.steepness, self.width, self.sf), self.depth()) + \
            self.operands[0].pretty_print() + \
            colored(')', self.depth())
            
    def latex_print(self):
        return 'BL\\left( ' + ' , '.join([e.latex_print() for e in self.operands]) + ' \\right)'            
            
    def __repr__(self):
        return 'BlackoutKernel(location=%f, steepness=%f, width=%f, sf=%f, operands=%s)' % \
            (self.location, self.steepness, self.width, self.sf, '[ ' + ', '.join([o.__repr__() for o in self.operands]) + ' ]')                
    
    def gpml_kernel_expression(self):
        return '{@covBlackout, {%s}}' % ', '.join(e.gpml_kernel_expression() for e in self.operands)
    
    def copy(self):
        return BlackoutKernel(self.location, self.steepness, self.width, self.sf [e.copy() for e in self.operands])

    def param_vector(self):
        return np.concatenate([np.array([self.location, self.steepness, self.width, self.sf])] + [e.param_vector() for e in self.operands])
        
    def effective_params(self):
        return 4 + sum([o.effective_params() for o in self.operands])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Returns the parameter vector with any default values replaced with random Gaussian'''
        result = self.param_vector()[:4]
        if result[0] == 0: #### TODO - Make sure this default matches that in self.default() - should do when on log scale
            # Location moves with input location, and variance scales in input variance
            # Expect change points to occur with the data
            #### TODO - check us for sensibleness!
            result[0] = np.random.normal(loc=data_shape['input_location'], scale=0.5*sd*np.exp(data_shape['input_scale']))
        if result[1] == 0:
            # Set steepness with inverse input scale
            #### TODO - is this correct scaling?
            result[1] = np.random.normal(loc=4-np.log((data_shape['input_max'] - data_shape['input_min'])), scale=0.5*sd)
        if result[2] == 0:
            # Set width with input scale
            #### TODO - is this correct scaling?
            result[2] = np.random.normal(loc=np.log(0.1)+data_shape['input_scale'], scale=0.5*sd)
        if result[3] == 0:
            # Set sf with output scale
            result[3] = np.random.normal(loc=data_shape['output_scale'], scale=sd)
        return np.concatenate([result] + [o.default_params_replaced(sd=sd, data_shape=data_shape) for o in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp((self.location, self.steepness, self.width, self.sf, self.operands),
                   (other.location, other.steepness, other.width, other.sf, other.operands))
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1
            
    def out_of_bounds(self, constraints):#### TODO - check me!
        return (self.location < constraints['input_min'] + 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.location > constraints['input_max'] - 0.0 * (constraints['input_max'] -constraints['input_min'])) or \
               (self.width > np.log(0.25*(constraints['input_max'] -constraints['input_min']))) or \
               (self.steepness < -np.log((constraints['input_max'] -constraints['input_min'])) + 3) or \
               (any([o.out_of_bounds(constraints) for o in self.operands])) 
        
class SumKernelFamily(KernelFamily):
    def __init__(self, operands):
        self.operands = operands
        
    def from_param_vector(self, params):
        start = 0
        ops = []
        for e in self.operands:
            end = start + e.num_params()
            ops.append(e.from_param_vector(params[start:end]))
            start = end
        return SumKernel(ops)
    
    def num_params(self):
        return sum([e.num_params() for e in self.operands])
    
    def pretty_print(self):
        op = colored(' + ', self.depth())
        return colored('( ', self.depth()) + \
            op.join([e.pretty_print() for e in self.operands]) + \
            colored(' ) ', self.depth())
    
    def default(self):
        return SumKernel([op.default() for op in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp(self.operands, other.operands)
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1

class SumKernel(Kernel):
    def __init__(self, operands):
        self.operands = operands
        
    def family(self):
        return SumKernelFamily([e.family() for e in self.operands])
        
    def pretty_print(self):
        #### Should this call the family method?
        op = colored(' + ', self.depth())
        return colored('( ', self.depth()) + \
            op.join([e.pretty_print() for e in self.operands]) + \
            colored(' ) ', self.depth())
            
    def latex_print(self):
        return '\\left( ' + ' + '.join([e.latex_print() for e in self.operands]) + ' \\right)'            
            
    def __repr__(self):
        return 'SumKernel(%s)' % \
            ('[ ' + ', '.join([o.__repr__() for o in self.operands]) + ' ]')                
    
    def gpml_kernel_expression(self):
        return '{@covSum, {%s}}' % ', '.join(e.gpml_kernel_expression() for e in self.operands)
    
    def copy(self):
        return SumKernel([e.copy() for e in self.operands])

    def param_vector(self):
        return np.concatenate([e.param_vector() for e in self.operands])
        
    def effective_params(self):
        return sum([o.effective_params() for o in self.operands])
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Returns the parameter vector with any default values replaced with random Gaussian'''
        return np.concatenate([o.default_params_replaced(sd=sd, data_shape=data_shape) for o in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp(self.operands, other.operands)
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1
    
    def __add__(self, other):
        assert isinstance(other, Kernel)
        if isinstance(other, SumKernel):
            return SumKernel(self.operands + other.operands).copy()
        else:
            return SumKernel(self.operands + [other]).copy()
            
    def out_of_bounds(self, constraints):
        return any([o.out_of_bounds(constraints) for o in self.operands]) 
    
class ProductKernelFamily(KernelFamily):
    def __init__(self, operands):
        self.operands = operands
        
    def from_param_vector(self, params):
        start = 0
        ops = []
        for o in self.operands:
            end = start + o.num_params()
            ops.append(o.from_param_vector(params[start:end]))
            start = end
        return ProductKernel(ops)
    
    def num_params(self):
        return sum([e.num_params() for e in self.operands])
    
    def pretty_print(self):
        op = colored(' x ', self.depth())
        return colored('( ', self.depth()) + \
            op.join([e.pretty_print() for e in self.operands]) + \
            colored(' ) ', self.depth())
    
    def default(self):
        return ProductKernel([op.default() for op in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, KernelFamily)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp(self.operands, other.operands)
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1
        
        
class ProductKernel(Kernel):
    def __init__(self, operands):
        self.operands = operands
        
    def family(self):
        return ProductKernelFamily([e.family() for e in self.operands])
        
    def pretty_print(self):
        #### Should this call the family method?
        op = colored(' x ', self.depth())
        return colored('( ', self.depth()) + \
            op.join([e.pretty_print() for e in self.operands]) + \
            colored(' ) ', self.depth())

    def latex_print(self):
        #return '\\left( ' + ' \\times '.join([e.latex_print() for e in self.operands]) + ' \\right)'
        # Don't need brackets for product, order of operations is unambiguous, I think.
        return ' \\times '.join([e.latex_print() for e in self.operands])
            
    def __repr__(self):
        return 'ProductKernel(%s)' % \
            ('[ ' + ', '.join([o.__repr__() for o in self.operands]) + ' ]')              
    
    def gpml_kernel_expression(self):
        return '{@covProd, {%s}}' % ', '.join(e.gpml_kernel_expression() for e in self.operands)
    
    def copy(self):
        return ProductKernel([e.copy() for e in self.operands])

    def param_vector(self):
        return np.concatenate([e.param_vector() for e in self.operands])
        
    def effective_params(self):
        '''The scale of a product of kernels is over parametrised'''
        return sum([o.effective_params() for o in self.operands]) - (len(self.operands) - 1)
        
    def default_params_replaced(self, sd=1, data_shape=None):
        '''Returns the parameter vector with any default values replaced with random Gaussian'''
        return np.concatenate([o.default_params_replaced(sd=sd, data_shape=data_shape) for o in self.operands])
    
    def __cmp__(self, other):
        assert isinstance(other, Kernel)
        if cmp(self.__class__, other.__class__):
            return cmp(self.__class__, other.__class__)
        return cmp(self.operands, other.operands)
    
    def depth(self):
        return max([op.depth() for op in self.operands]) + 1
    
    def __mul__(self, other):
        assert isinstance(other, Kernel)
        if isinstance(other, ProductKernel):
            return ProductKernel(self.operands + other.operands).copy()
        else:
            return ProductKernel(self.operands + [other]).copy()
            
    def out_of_bounds(self, constraints):
        return any([o.out_of_bounds(constraints) for o in self.operands]) 


#### FIXME - Sort out the naming of the two functions below            
def base_kernels(ndim=1, base_kernel_names='SE'):
    '''
    Generator of all base kernels for a certain dimensionality of data
    '''
    
    #### FIXME - special behaviour
    if 'BurstSE' in base_kernel_names:
        for dim in range(ndim):
            yield BurstKernelFamily([MaskKernelFamily(ndim, dim, SqExpKernelFamily())]).default()
    
    for dim in range(ndim):
        for fam in base_kernel_families(base_kernel_names):
            yield MaskKernel(ndim, dim, fam.default())
    #if ndim == 1:
    #    for k in base_kernel_families(ndim):
    #        yield MaskKernel(ndim, 0, k)
    #        # Todo: fix 1D kernels to work without MaskKernels.
    #else:
    #    for dim in range(ndim):
    #        for k in multi_d_kernel_families():
    #            yield MaskKernel(ndim, dim, k)
 
def base_kernel_families(base_kernel_names):
    '''
    Generator of all base kernel families.
    '''
    for family in [SqExpKernelFamily(), \
                   SqExpPeriodicKernelFamily(), \
                   RQKernelFamily(), \
                   ConstKernelFamily(), \
                   LinKernelFamily(), \
                   ChangeKernelFamily(), \
                   QuadraticKernelFamily(), \
                   CubicKernelFamily(), \
                   PP0KernelFamily(), \
                   PP1KernelFamily(), \
                   PP2KernelFamily(), \
                   PP3KernelFamily(), \
                   Matern1KernelFamily(), \
                   Matern3KernelFamily(), \
                   Matern5KernelFamily(), \
                   CosineKernelFamily(), \
                   SpectralKernelFamily(), \
                   IBMKernelFamily(), \
                   IBMLinKernelFamily(), \
                   StepKernelFamily()]:
        if family.id_name() in base_kernel_names.split(','):
            yield family
    #if ndim == 1:
    #    yield SqExpKernelFamily().default()
    #    yield SqExpPeriodicKernelFamily().default()
    #    yield RQKernelFamily().default()
    #    yield LinKernelFamily().default()
    #    #yield ChangeKernelFamily().default()
    #else:
    #    yield SqExpKernelFamily().default()
    #    yield SqExpPeriodicKernelFamily().default()
    #    yield RQKernelFamily().default()
    #    yield LinKernelFamily().default()
    #yield QuadraticKernelFamily().default()
    #yield CubicKernelFamily().default()
    #yield PP0KernelFamily().default()
    #yield PP1KernelFamily().default()
    #yield PP2KernelFamily().default()
    #yield PP3KernelFamily().default()
    #yield MaternKernelFamily().default()       

#def multi_d_kernel_families():
#    '''
#    Generator of all base kernel families for multidimensional problems.
#    '''
#    yield SqExpKernelFamily().default()
#    yield SqExpPeriodicKernelFamily().default()
#    yield RQKernelFamily().default()
#    yield LinKernelFamily().default()  
   
   
#### FIXME - Do the two functions below get called ever?        
def test_kernels(ndim=1):
    '''
    Generator of a subset of base kernels for testing
    '''
    for dim in range(ndim):
        for k in test_kernel_families():
            yield MaskKernel(ndim, dim, k) 
         
def test_kernel_families():
    '''
    Generator of all base kernel families
    '''
    yield SqExpKernelFamily().default()
    #yield SqExpPeriodicKernelFamily().default() 
    #yield RQKernelFamily().default()       

def Carls_Mauna_kernel():
    '''
    This kernel described in pages 120-122 of "Gaussian Processes for Machine Learning.
    This model was learnt on the mauna dataset up to 2003.
    
    The reported nll in the book for this dataset is 108.5
    '''
    theta_1 = np.log(66.)  # ppm, sf of SE1 = magnitude of long term trend
    theta_2 = np.log(67.)  # years, ell of SE1 = lengthscale of long term trend
    theta_6 = np.log(0.66)  # ppm, sf of RQ = magnitude of med term trend
    theta_7 = np.log(1.2)  # years, ell of RQ = lengthscale of med term trend
    theta_8 = np.log(0.78) # alpha of RQ
    theta_3 = np.log(2.4) # ppm, sf of periodic * SE
    theta_4 = np.log(90.) # years, lengthscale of SE of periodic*SE
    theta_5 = np.log(1.3) # smoothness of periodic
    theta_9 = np.log(0.18) # ppm, amplitude of SE_noise
    theta_10 = np.log(1.6/12.0) # years (originally months), lengthscale of SE_noise
    theta_11 = np.log(0.19) # ppm, amplitude of independent noise
    
    kernel = SqExpKernel(output_variance=theta_1, lengthscale=theta_2) \
           + SqExpKernel(output_variance=theta_3, lengthscale=theta_4) * SqExpPeriodicKernel(output_variance=0, period=0, lengthscale=theta_5) \
           + RQKernel(lengthscale=theta_7, output_variance=theta_6, alpha=theta_8) \
           + SqExpKernel(output_variance=theta_9, lengthscale=theta_10)
    
    return kernel


def strip_masks(k):
    """Recursively strips masks out of a kernel, for when we used a multi-d grammar on a 1d problem."""    
    if isinstance(k, MaskKernel):
        return strip_masks(k.base_kernel)
    elif isinstance(k, SumKernel):
        return SumKernel([strip_masks(op) for op in k.operands])
    elif isinstance(k, ProductKernel):
        return ProductKernel([strip_masks(op) for op in k.operands])
    else:
        return k  

def break_kernel_into_summands(k):
    '''Takes a kernel, expands it into a polynomial, and breaks terms up into a list.
    
    Mutually Recursive with distribute_products().
    Always returns a list.
    '''    
    # First, recursively distribute all products within the kernel.
    k_dist = distribute_products(k)
    
    if isinstance(k_dist, SumKernel):
        # Break the summands into a list of kernels.
        return list(k_dist.operands)
    else:
        return [k_dist]

def distribute_products(k):
    """Distributes products to get a polynomial.
    
    Mutually recursive with break_kernel_into_summands().
    Always returns a sumkernel.
    """

    if isinstance(k, ProductKernel):
        # Recursively distribute each of the terms to be multiplied.
        distributed_ops = [break_kernel_into_summands(op) for op in k.operands]
        
        # Now produce a sum of all combinations of terms in the products. Itertools is awesome.
        new_prod_ks = [ProductKernel( prod ) for prod in itertools.product(*distributed_ops)]
        return SumKernel(new_prod_ks)
    
    elif isinstance(k, SumKernel):
        # Recursively distribute each the operands to be summed, then combine them back into a new SumKernel.
        return SumKernel([subop for op in k.operands for subop in break_kernel_into_summands(op)])
    elif isinstance(k, ChangePointKernel):
        return SumKernel([ChangePointKernel(location=k.location, steepness=k.steepness, operands=[op, ZeroKernel()]) for op in break_kernel_into_summands(k.operands[0])] + \
                         [ChangePointKernel(location=k.location, steepness=k.steepness, operands=[ZeroKernel(), op]) for op in break_kernel_into_summands(k.operands[1])])
    elif isinstance(k, BurstKernel):
        return SumKernel([BurstKernel(location=k.location, steepness=k.steepness, width=k.width, operands=[op]) for op in break_kernel_into_summands(k.operands[0])])
    elif isinstance(k, BurstKernel):
        return SumKernel([BlackoutKernel(location=k.location, steepness=k.steepness, width=k.width, sf=k.sf-np.log(len(break_kernel_into_summands(k.operands[0]))), operands=[op]) for op in break_kernel_into_summands(k.operands[0])])
    else:
        # Base case: A kernel that's just, like, a kernel, man.
        return k
        
from numpy import nan

def repr_string_to_kernel(string):
    """This is defined in this module so that all the kernel class names
    don't have to have the module name in front of them."""
    return eval(string)

class ScoredKernel:
    '''
    Wrapper around a kernel with various scores and noise parameter
    '''
    def __init__(self, k_opt, nll=nan, laplace_nle=nan, bic_nle=nan, npll=nan, pic_nle=nan, mae=nan, std_ratio=nan, noise=nan):
        self.k_opt = k_opt
        self.nll = nll
        self.laplace_nle = laplace_nle
        self.bic_nle = bic_nle
        self.npll = npll
        self.pic_nle = pic_nle
        self.mae = mae
        self.std_ratio = std_ratio
        self.noise = noise
        
    #### CAUTION - the default keeps on changing!
    def score(self, criterion='bic'):
        return {'bic': self.bic_nle,
                'nll': self.nll,
                'laplace': self.laplace_nle,
                'npll': self.npll,
                'pic': self.pic_nle,
                'mae': self.mae
                }[criterion]
                
    @staticmethod
    def from_printed_outputs(nll, laplace, BIC, npll, PIC, mae, std_ratio, noise=None, kernel=None):
        return ScoredKernel(kernel, nll, laplace, BIC, npll, PIC, mae, std_ratio, noise)
    
    def __repr__(self):
        return 'ScoredKernel(k_opt=%s, nll=%f, laplace_nle=%f, bic_nle=%f, npll=%f, pic_nle=%f, mae=%f, std_ratio=%f, noise=%s)' % \
            (self.k_opt, self.nll, self.laplace_nle, self.bic_nle, self.npll, self.pic_nle, self.mae, self.std_ratio, self.noise)

    def pretty_print(self):
        return self.k_opt.pretty_print()

    def latex_print(self):
        return self.k_opt.latex_print()

    @staticmethod	
    def from_matlab_output(output, kernel_family, ndata):
        '''Computes Laplace marginal lik approx and BIC - returns scored Kernel'''
        #laplace_nle, problems = psd_matrices.laplace_approx_stable(output.nll, output.kernel_hypers, output.hessian)
        #### TODO - this check should be within the psd_matrices code
        if np.any(np.isnan(output.hessian)):
            laplace_nle = np.nan
        else:
            #### TODO - reinstate me
            #laplace_nle = psd_matrices.laplace_approx_no_prior(output.nll, np.concatenate((output.kernel_hypers, output.noise_hyp)), output.hessian)
            laplace_nle = np.nan
        k_opt = kernel_family.from_param_vector(output.kernel_hypers)
        BIC = 2 * output.nll + k_opt.effective_params() * np.log(ndata)
        PIC = 2 * output.npll + k_opt.effective_params() * np.log(ndata)
        return ScoredKernel(k_opt, output.nll, laplace_nle, BIC, output.npll, PIC, output.mae, output.std_ratio, output.noise_hyp)	

def replace_defaults(param_vector, sd):
    #### FIXME - remove dependence on special value of zero
    ####       - Caution - remember print, compare etc when making the change (e.g. just replacing 0 with None would cause problems later)
    '''Replaces zeros in a list with Gaussians'''
    return [np.random.normal(scale=sd) if p ==0 else p for p in param_vector]

def add_random_restarts_single_kernel(kernel, n_rand, sd, data_shape):
    '''Returns a list of kernels with random restarts for default values'''
    #return [kernel] + list(itertools.repeat(kernel.family().from_param_vector(replace_defaults(kernel.param_vector(), sd)), n_rand))
    return [kernel] + list(map(lambda unused : kernel.family().from_param_vector(kernel.default_params_replaced(sd=sd, data_shape=data_shape)), [None] * n_rand))

def add_random_restarts(kernels, n_rand=1, sd=4, data_shape=None):    
    '''Augments the list to include random restarts of all default value parameters'''
    return [k_rand for kernel in kernels for k_rand in add_random_restarts_single_kernel(kernel, n_rand, sd, data_shape)]