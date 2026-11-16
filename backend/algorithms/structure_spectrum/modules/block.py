
from torch import nn
from .update import Update
from .message import Message
from .block_bond import block_bond
from torch_scatter import scatter
class Interaction_Block(nn.Module):

    def __init__(self,
                 num_features,
                 act,
                 head,
                 num_radial,
                 irreps_sh,
                 irreps_T,
                 vdim,
                 ):
        super(Interaction_Block,self).__init__()
        # 原子消息传递、更新
        self.message=Message(head=head,num_radial=num_radial,  act=act,
                             num_features=num_features,irreps_sh=irreps_sh)
        self.update=Update(num_features=num_features,act=act,
                            irreps_mout=self.message.tp.irreps_out,
                           irreps_T=irreps_T)
        # 化学键消息传递更新
        self.bond_block = block_bond(num_features=num_features,
                                        head = head,
                                        vdim=vdim,
                                        act=act)

    def forward(self,S,T,rbf,sh,index,
                bonds_emb,
                edge_attr,
                bonds_edge_index):
        # 原子MPNN
        mijt,mijs=self.message(S=S,rbf=rbf,sh=sh,index=index)
        T,S=self.update(T=T,S=S,mijt=mijt,mijs=mijs,index=index)   
        # 化学键MPNN     
        bonds_emb = self.bond_block(bonds_emb,bonds_edge_index,edge_attr)
        return S,T,bonds_emb
if __name__ == "__main__":
    pass
