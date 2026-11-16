import torch.nn as nn 
from .acts import activations
from torch_scatter import scatter
import torch
class block_bond(nn.Module):

    def __init__(self,  num_features,
                        head,
                        vdim,
                        act='relu'):
        super(block_bond, self).__init__()
        self.num_features = num_features
        self.act = act
        self.vdim = vdim
        self.head = head
        self.softmax=activations('softmax')
        self.path_weight_emb = self.path_weight_emb = nn.Sequential(nn.Linear(8,int(num_features/2)),
                                    activations(act,num_features=int(num_features/2)),
                                    nn.Linear(int(num_features/2),int(num_features)),
                                    activations(act,num_features=int(num_features)))
        self.mj1 = nn.Linear(num_features,num_features)
        self.mk1 = nn.Linear(num_features,num_features)
        self.mi1 = nn.Linear(num_features,num_features)
        self.mk2 = nn.Linear(num_features,num_features)

        self.lpathj1 = nn.Linear(num_features,num_features,bias=False)
        self.lpathk1 = nn.Linear(num_features,num_features,bias=False)
        self.lpathi1 = nn.Linear(num_features,num_features,bias=False)
        self.lpathk2 = nn.Linear(num_features,num_features,bias=False)

        self.lmi = nn.Sequential(nn.Linear(int(num_features*2) ,int(num_features*2),bias=False),
                                activations(act,num_features=int(num_features*2)))
        self.reset_parameters()
    def reset_parameters(self):
        for l in self.modules():
            if isinstance(l,nn.Linear):
                nn.init.xavier_uniform_(l.weight)
                if l.bias is not None:
                    l.bias.data.fill_(0)


    def forward(self,bonds_emb,edge_index,edge_attr):
        '''
        edge_index: size([3,m])
        x: size([n,3])
        x_emb: size([n,emb_dim])
        edge_attr: size([m,8]) 
        '''
        i_,j_,k_ = edge_index

        path_weight = self.path_weight_emb(edge_attr)
        mi_ = self.mj1(bonds_emb[j_])*self.lpathj1(path_weight)\
                 + self.mk1(bonds_emb[k_]) * self.lpathk1(path_weight) 
        mj_ = self.mi1(bonds_emb[i_])*self.lpathi1(path_weight)\
                 + self.mk2(bonds_emb[k_]) * self.lpathk2(path_weight)
        bonds_emb = bonds_emb+ scatter(src=torch.cat([mi_,mj_],dim=0),
                                index=torch.cat([i_,j_],dim=0),dim=0)
        # # k -> j -> i
        # # k -> j <- i

        return bonds_emb
if __name__ == "__main__":
    pass
