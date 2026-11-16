from torch import nn,device,tensor,float32
from .acts import activations
def get_elec_feature(max_atomic_number,device):
    # 原子电子层
    elec_feature = tensor(
        # P:Pair electron
        # S:Single electron
        #|  1s |  2s |  2p |  3s |  3p |  4s |  3d |  4p |
        # P  S  P  S  P  S  P  S  P  S  P  S  P  S  P  S
        [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 0 None
         [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 1 H
         [2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 2 He
         [2, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 3 Li
         [2, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 4 Be
         [2, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 5 B
         [2, 0, 2, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 6 C
         [2, 0, 2, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 7 N
         [2, 0, 2, 0, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 8 O
         [2, 0, 2, 0, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 9 F
         [2, 0, 2, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 10 Ne
         [2, 0, 2, 0, 6, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 11 Na
         [2, 0, 2, 0, 6, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, ],  # 12 Me
         [2, 0, 2, 0, 6, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 0, ],  # 13 Al
         [2, 0, 2, 0, 6, 0, 2, 0, 0, 2, 0, 0, 0, 0, 0, 0, ],  # 14 Si
         [2, 0, 2, 0, 6, 0, 2, 0, 0, 3, 0, 0, 0, 0, 0, 0, ],  # 15 P
         [2, 0, 2, 0, 6, 0, 2, 0, 2, 2, 0, 0, 0, 0, 0, 0, ],  # 16 S
         [2, 0, 2, 0, 6, 0, 2, 0, 4, 1, 0, 0, 0, 0, 0, 0, ],  # 17 Cl
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 0, 0, 0, 0, 0, 0, ],  # 18 Ar
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 0, 1, 0, 0, 0, 0, ],  # 19 K
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 0, 0, 0, 0, ],  # 20 Ca
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 0, 1, 0, 0, ],  # 21 Sc
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 0, 2, 0, 0, ],  # 22 Ti
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 0, 3, 0, 0, ],  # 23 V
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 0, 1, 0, 5, 0, 0, ],  # 24 Cr
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 0, 5, 0, 0, ],  # 25 Mn
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 2, 4, 0, 0, ],  # 26 Fe
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 4, 3, 0, 0, ],  # 27 Co
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0, 6, 2, 0, 0, ],  # 28 Ni
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 0, 1,10, 0, 0, 0, ],  # 29 Cu
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0,10, 0, 0, 0, ],  # 30 Zn
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0,10, 0, 0, 1, ],  # 31 Ga
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0,10, 0, 0, 2, ],  # 32 Ge
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0,10, 0, 0, 3, ],  # 33 As
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0,10, 0, 2, 2, ],  # 34 Se
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0,10, 0, 4, 1, ],  # 35 Br
         [2, 0, 2, 0, 6, 0, 2, 0, 6, 0, 2, 0,10, 0, 6, 0, ],  # 36 Kr
         ], dtype=float32)
    elec=elec_feature[0:max_atomic_number+1]
    return (elec/elec.max()).to(device)
# 原子特征嵌入
class Embedding(nn.Module):
    def __init__(self,num_features,act,max_atomic_number=9,device=device('cuda')):
        super(Embedding,self).__init__()
        # 原子电子排布信息嵌入
        self.elec=get_elec_feature(max_atomic_number=max_atomic_number,device=device)
        self.act=activations(type=act,num_features=num_features)
        self.elec_emb = nn.Linear(16, num_features, bias=False)
        # 原子类型嵌入
        self.nuclare_emb = nn.Embedding(max_atomic_number+1, num_features)
        self.ls = nn.Linear(num_features, num_features)
        self.reset_parameters()

    def reset_parameters(self):
        nn.init.xavier_uniform_(self.ls.weight)
        self.ls.bias.data.fill_(0)
        self.nuclare_emb.reset_parameters()
        nn.init.xavier_uniform_(self.elec_emb.weight)

    def forward(self,z):
        return self.act(self.ls(self.nuclare_emb(z)+self.elec_emb(self.elec[z,:])))
# 化学键特征嵌入
class Bond_embedding(nn.Module):
    def __init__(self,num_features,act):
        super(Bond_embedding,self).__init__()
        self.bonds_init = nn.Sequential(nn.Linear(4,int(num_features/4)),
                                    activations(act,num_features=int(num_features/4)),
                                    nn.Linear(int(num_features/4),int(num_features/2)),
                                    activations(act,num_features=int(num_features/2)))
        self.bonds_emb_1 = nn.Linear(int(num_features/2),num_features)
        self.bonds_emb_2 = nn.Linear(int(num_features/2),num_features)
        self.bonds_emb_out = nn.Sequential(nn.Linear(num_features, num_features),
                                    activations(type=act,num_features=num_features))

        self.reset_parameters()

    def reset_parameters(self):
        for l in self.modules():
            if isinstance(l,nn.Linear):
                nn.init.xavier_uniform_(l.weight)
                if l.bias is not None:
                    l.bias.data.fill_(0)

    def forward(self,bonds_x):
        bonds_x = self.bonds_init(bonds_x)
        return self.bonds_emb_out(self.bonds_emb_1(bonds_x)+self.bonds_emb_2(bonds_x))
if __name__ == "__main__":
    pass
