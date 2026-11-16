from e3nn import o3
import torch
from torch import nn
from .edge_attention import Edge_Attention

class Message(nn.Module):
    def __init__(self,head,num_radial,num_features,irreps_sh,act):
        super(Message,self).__init__()
        self.feature=num_features
        self.Attention=Edge_Attention(head=head,num_radial=num_radial,num_features=num_features,act=act)
        irreps_mout = []
        instructions = []
        # 由标量特征与不规则张量生成的不规则张量特征的张量积
        # 取一个128维的标量和一个张量，
        for i, (_, ir_sh) in enumerate(irreps_sh):
            for ir_out in o3.Irrep('0e') * ir_sh:
                k = len(irreps_mout)
                irreps_mout.append((num_features, ir_out))
                instructions.append((0, i, k, "uvu", True))
        self.tp = o3.TensorProduct(irreps_in1=o3.Irreps([(num_features, (0, 1))]), irreps_in2=irreps_sh,
                                   irreps_out=irreps_mout, instructions=instructions, shared_weights=True,
                                   internal_weights=True)

    def forward(self,S,rbf,sh,index):
        # 第一不变特征和径向特征通过注意机制生成边缘特征
        eij=self.Attention(S=S,rbf=rbf,index=index)
        # 然后将边缘特征eij分成两部分，一部分作为不变特征的输出，
        # 另一部分与球调和函数生成的不重复张量积输出等变特征
        mijs2,mijs=torch.split(eij,split_size_or_sections=[self.feature, self.feature],dim=-1)
        mijt=self.tp(mijs2,sh)
        return mijt,mijs

if __name__ == "__main__":
    pass
