"""Vibrational analysis and spectral broadening from the original predictor."""
import torch
from .constant import *

def hessfreq(Hi, Hij, edge_index, masses, normal=False, linear=False, scale=0.965):
    '''Combine the Hessian matrices of the Hi and Hij parts and calculate the frequencies and normal coordinates

    normal:Whether or not to normalize the normal coordinates,Default: False

    linear:Is it a linear molecule? Default: False

    scale:Correction factor for frequency.Default:0.965

    It is worth mentioning that the output frequency may generate NaN in the first frequency,
    which corresponds to the negative frequency in quantum chemistry calculations, Simply delete this frequency.
    '''

    # Calculating the masses matrix
    wmasses = torch.pow(masses.to(Hi.device), -0.5).repeat_interleave(3, dim=0)
    wmat = wmasses[:, None]*wmasses[None, :]

    # Construction of hessian matrix by atomic part and interatomic part
    i, j = edge_index
    dia = torch.arange(0, len(Hi), step=1, device=Hi.device, dtype=int)
    hessian = torch.zeros(
        size=(Hi.shape[0], 3, Hi.shape[0], 3), device=Hi.device)
    hessian[j, :, i, :] = Hij
    hessian[dia, :, dia, :] = Hi
    hessian = hessian.reshape(Hi.shape[0]*3, Hi.shape[0]*3)

    # predicted hesssian matrix (ij part) may be asymmetric,we take the average of two directions to make it symmetric
    hessian = (hessian+hessian.permute(1, 0))/2

    hessian = hessian*wmat

    # Diagonalisation
    eva, evec = torch.linalg.eigh(hessian)
    eva = eva * hess_t

    negative_indices = eva < 0
    positive_indices = eva >= 0
    freq = torch.zeros_like(eva)
    
    freq[negative_indices] = -torch.pow(torch.abs(eva[negative_indices]), 0.5) / (2 * torch.pi)
    freq[positive_indices] = torch.pow(eva[positive_indices], 0.5) / (2 * torch.pi)

    # freq = torch.pow(eva, 0.5) / (2 * torch.pi)
    freq = freq/cm_hz
    p = -evec.t()*wmasses
    normals = torch.norm(p, dim=1).unsqueeze(1)
    if normal:
        p = p/normals
    p = p.reshape(len(freq), -1, 3)
    if scale is not None:
        freq = freq*scale
    if linear:
        return freq[5:], p[5:]
    else:
        return freq[6:], p[6:]

def chain_rule_raman(dp, modes):
    '''Calculation of raman tensor by the chain rule
    The input polarizability derivatives unit are 'a0**3/A',
    '''
    ramans = (modes[..., None]*dp[None, :, :, :]
              ).reshape(modes.shape[0], -1, 6)
    raman_tensor = torch.sum(ramans, dim=1)
    return raman_tensor

def get_raman_act(raman_tensor):
    '''Calculation of Raman activity from the Raman tensor
    calculate by 45x(alpha**2)+7x(gamma**2)  alpha and gamma represent isotropic and anisotropic part of Raman tensor
    The output Raman activity is in units of A**4/Amu(Consistent with gaussian g16)
    '''
    xx = raman_tensor[:, 0]
    xy = raman_tensor[:, 1]
    yy = raman_tensor[:, 2]
    xz = raman_tensor[:, 3]
    zy = raman_tensor[:, 4]
    zz = raman_tensor[:, 5]
    alpha = (xx+yy+zz)/3
    gamma_sq1 = 0.5*(((xx-yy)**2)+((yy-zz)**2)+((zz-xx)**2))
    gamma_sq2 = 3*((xy**2)+(xz**2)+(zy**2))
    gamma_sq = gamma_sq1+gamma_sq2
    return (45*(alpha**2)+7*gamma_sq)*raman_coff

def get_raman_intensity(freq, raman_act, temp=298, init_wl=532):
    '''Raman intensity is calculated from the Raman activity and frequency,temperature and incident light Wavelength.
     The output Raman intensity is unitless.
     Unfortunately, 32-float is not sufficient for Raman calculations and only 64-float can be used to calculate Raman
     '''
    init_freq_si = cm_hz / (init_wl * 1e-7)
    freq_si = freq.to(torch.float64)*cm_hz
    act_si = raman_act.to(torch.float64)*(A_m**4)/45
    last = 1/(1-torch.exp(-hp*c*freq_si/(Kb*temp)))
    dv = ((init_freq_si-freq_si)**4)/freq_si
    return act_si*dv*last

def Lorenz_broadening(x0, y0, c=torch.linspace(500, 4000, 3501), sigma=12):
    '''Lorenz broadening for Vibration and NMR spectroscopies
    x0 y0:Position of the horizontal and vertical axes to be broadening

    c:Position of the broadening horizontal axis and number of points

    sigma:spread half width

    The position of the vertical axis after the output has been broadened.
    '''
    lx = x0[:, None]-c[None, :]
    ly = (sigma/(2*3.1415926))/(lx**2 + 0.25*(sigma**2))
    y = torch.sum(y0[:, None]*ly, dim=0)
    return y.view(-1)

def freqaraman2spec(freq, araman):
    x_axis = torch.linspace(500, 4000, 3501)
    yraman_act = Lorenz_broadening(freq, araman, c=x_axis, sigma=12)
    # get raman intensity from raman act,frequency
    yraman = get_raman_intensity(x_axis, yraman_act).detach().numpy()
    x = x_axis.detach().numpy()
    return x_axis, yraman
