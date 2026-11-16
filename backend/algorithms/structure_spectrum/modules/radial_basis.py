import torch
from torch import nn

class Bessel_Function(nn.Module):
    '''
    贝塞尔径向基函数
    '''
    def __init__(self,num_radial,rc,inital_beta=2.0):
        super(Bessel_Function,self).__init__()
        assert rc !=0
        self.register_parameter('alpha',
                                    nn.Parameter(torch.arange(0,num_radial,dtype=torch.float32).view(1,num_radial)))
        self.register_parameter('beta',nn.Parameter(torch.Tensor(1,num_radial)))
        nn.init.constant_(self.beta,inital_beta)
        self.rc=rc
        self.prefactor=(2 /rc) ** 0.5
    def forward(self,r):
        r = r.view(-1, 1)
        rbf = self.prefactor * torch.sin(self.alpha*torch.pi * r / self.rc) /(self.beta*r)
        return rbf
    
class Radial_Basis(nn.Module):
    '''
    径向基函数上层封装
    '''
    def __init__(self,num_radial=32,rc=5.0):
        super(Radial_Basis,self).__init__()
        self.radial=Bessel_Function(num_radial=num_radial,rc=rc)
    def forward(self,r):
        return self.radial(r)

if __name__ == "__main__":
    pass
