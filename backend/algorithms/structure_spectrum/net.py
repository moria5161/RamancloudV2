import torch
from e3nn import o3,io
from torch import nn,FloatTensor
from .constant import atom_masses
from torch_geometric.nn import radius_graph
from .modules import Interaction_Block,Embedding,Bond_embedding, Radial_Basis,MLP,Equivariant_Multilayer,activations
from torch.autograd import grad
from torch_scatter import scatter


class Net(nn.Module):
    def __init__(self,num_features=128,
                 act='swish',
                 maxl=3,
                 num_block=3,
                 num_radial=32,
                 attention_head=8,
                 rc:float=5.0,
                 max_atomic_number=35,
                 scalar_outsize=1,
                 irreps_out=None,
                 summation=True,
                 out_type='scalar',
                 grad_type=None,
                 device=torch.device('cuda')):                
        super(Net,self).__init__()
        '''
        num_features : 节点特征嵌入维度
        act : 激活函数类型
        maxl :  特征的最大程度,默认为3。表示等变张量
        num_block : 网络层数
        num_radial : 径向基函数的嵌入维度
        attention_head : 多层注意力头数
        rc : 原子间距离截至距离
        max_atomic_number : 原子类别
        scalar_outsize : 模型输出维度
        irreps_out: 输出的向量或者张量类型，
        summation : 是否进行节点特征池化
        out_type : 输出类型是标量还是向量,由一个非负整数和一个包含字母'o','e'的字符串组成。数字代表度，字母'o'表示奇数性，字母'e'表示偶数性。
        grad_type : 求偏导类型
        device : 模型存放设备
        '''
        assert num_features%attention_head==0,'attention head must be divisible by the number of features'
        self.summation=summation
        self.scalar_outsize=scalar_outsize
        self.out_type=out_type
        self.rc=rc
        self.grad=grad_type
        # 生成repp特征的表示
        irreps_T = o3.Irreps((num_features, (l, (-1) ** l)) for l in range(1, maxl + 1))
        self.vdim = o3.Irreps(irreps_T).dim
        self.features=num_features
        self.T=num_block
        self.irreps_out=irreps_out
        # 生成球谐函数
        irrs_sh=o3.Irreps.spherical_harmonics(lmax=maxl, p=-1)
        self.irreps_sh=irrs_sh[1:]
        # 生成化学键消息传递
        self.bond_emb = Bond_embedding(num_features,act)
        self.lcat_S = nn.Linear(num_features,num_features,bias=False)
        self.lcat_T = nn.Linear(num_features,self.vdim,bias=False)
        # 生成特征嵌入和径向基函数
        self.Embedding=Embedding(num_features=num_features,act=act,device=device,max_atomic_number=max_atomic_number)
        self.Radial=Radial_Basis(num_radial=num_radial,rc = rc)
        blocks = []
        # 生成两个消息传递视图
        for _ in range(num_block):
            block=Interaction_Block(num_features=num_features,
                        act=act,
                        head=attention_head,
                        num_radial=num_radial,
                        irreps_sh=self.irreps_sh,
                        irreps_T=irreps_T,
                        vdim=self.vdim,
                        )
            blocks.append(block)
        self.blocks=nn.Sequential(*blocks)

        if irreps_out is not None:
            mid = []
            for _, (l, p) in o3.Irreps(irreps_out):
                mid.append((num_features, (l, p)))
            irreps_mid = o3.Irreps(mid)
            self.tout=Equivariant_Multilayer(irreps_list=[irreps_T,irreps_mid,irreps_out],act=act)
        if scalar_outsize !=0:
            self.sout=MLP(size=(num_features,num_features,scalar_outsize),act=act)
        # 原子质量矩阵
        self.mass=atom_masses.to(device)

        if out_type == '2_tensor':
            self.ct = io.CartesianTensor('ij=ji')
        if self.grad=='polar':
            self.mask=torch.tril(torch.ones(size=(3,3)),diagonal=0).flatten()
            
    # 计算 分子的笛卡尔位移
    def centroid_coordinate(self, atoms_x, atoms_pos, atoms_batch):
        mass = self.mass[atoms_x].view(-1, 1)
        center_pos = scatter(mass * atoms_pos, atoms_batch, dim=0) / scatter(mass, atoms_batch, dim=0)
        ra = (atoms_pos - center_pos[atoms_batch])
        return ra

    # 映射至伪极化率向量
    def cal_p_tensor(self,atoms_x,atoms_pos,atoms_batch,outs,outt):
        sa,sb=torch.split(outs,dim=-1,split_size_or_sections=[1,1])
        ra=self.centroid_coordinate(atoms_x=atoms_x,atoms_pos=atoms_pos,atoms_batch=atoms_batch)
        ta=o3.spherical_harmonics(l=self.irreps_out,x=ra,normalize=False)*sa
        return self.ct.to_cartesian(torch.concat(tensors=(sb,outt+ta),dim=-1))
    # Hessian矩阵非对角线子矩阵求导
    def grad_hess_ij(self, energy, posj, posi, create_graph=True):
        fj = -grad([torch.sum(energy)], [posj], create_graph=create_graph)[0]
        Hji = torch.zeros((fj.shape[0], 3, 3), device=fj.device)
        for i in range(3):
            gji = -grad([fj[:, i].sum()], [posi], create_graph=create_graph, retain_graph=True)[0]
            Hji[:, i] = gji
        return Hji
    # Hessian矩阵对角线子矩阵求导
    def grad_hess_ii(self, energy, posa, posb, create_graph=True):
        f = -grad([torch.sum(energy)], [posa], create_graph=create_graph)[0]
        Hii = torch.zeros((f.shape[0], 3, 3), device=f.device)
        for i in range(3):
            gii = -grad([f[:, i].sum()], [posb], create_graph=create_graph, retain_graph=True)[0]
            Hii[:, i] = gii
        return Hii    
    # 极化率导数矩阵求导
    def grad_polarzability(self, polars, atoms_pos):
        polars = polars.flatten(start_dim=1)[:, self.mask == 1]
        depolar = torch.zeros(size=(atoms_pos.shape[0], 3, 6), device=atoms_pos.device)
        for i in range(0, 6):
            depolar[:, :, i] = -grad([polars[:, i].sum()], [atoms_pos], create_graph=True)[0]
        return depolar

    def forward(self,
                atoms_x,
                atoms_pos,
                atoms_edge_index,
                atoms_batch,
                bonds_x,
                bonds_edge_index,
                bonds_edge_attr,
                bonds_batch):
        '''
        atoms_x: shape = [n]; 原子类别矩阵
        atoms_pos: shape = [n,3]; 原子坐标矩阵
        atoms_edge_index = [2,m]; 原子消息传递视图邻接矩阵
        atoms_bacth: shape = [n]; 原子消息传递视图池化矩阵
        bonds_x: shape = [N, 4]; 化学键特征矩阵
        bonds_edge_index: shape = [3, M]; 化学键消息传递视图邻接矩阵
        bonds_edge_attr: shape = [M, 8]; 化学键消息传递视图边特征
        bonds_batch: shape = [N]; 化学键消息传递视图池化矩阵
        '''

        if self.grad is not None:
            atoms_pos.requires_grad=True

        # 嵌入原子节点特征
        S=self.Embedding(atoms_x)
        # 嵌入化学键节点特征

        bonds_emb = self.bond_emb(bonds_x)

        # 初始化0向量 
        T=torch.zeros(size=(S.shape[0],self.vdim),device=S.device,dtype=S.dtype)
        i,j= atoms_edge_index
        
        # 深拷贝原子坐标
        if self.grad=='Hi':
            posa=atoms_pos.clone()
            posb=atoms_pos.clone()
            posj = posa[j]
            posi = posb[i]
        else:
            posi=atoms_pos[i]
            posj=atoms_pos[j]
        # 生成原子间距离 
        rij = posj - posi
        r=torch.norm(rij,dim=-1)
        # 连续滤波卷积映射
        sh = o3.spherical_harmonics(l=self.irreps_sh, x=rij/(r.view(-1,1)), normalize=True, normalization="component")
        rbf = self.Radial(r)
        # 逐层原子消息传递和化学键消息传递
        for block in self.blocks:
            S,T,bonds_emb=block(S=S,T=T,rbf=rbf,sh=sh,index=atoms_edge_index,                        
                        bonds_emb   =   bonds_emb,
                        edge_attr =   bonds_edge_attr,
                        bonds_edge_index    =   bonds_edge_index)
        # 拼接原子消息传递视图分子表示向量和化学键消息传递视图分子表示向量
                
        bonds_emb_batch = scatter(src=bonds_emb,index=bonds_batch,dim=0)[atoms_batch]
        T = T + self.lcat_T(bonds_emb_batch)
        S = S + self.lcat_S(bonds_emb_batch)
        # 输入向量线性变换
        if self.irreps_out is not None:
            outt=self.tout(T)
        if self.scalar_outsize!=0:
            outs=self.sout(S)
            
        # 输出向量转换
        if self.out_type=='scalar':
            out=outs
        elif self.out_type=='2_tensor':
            out=self.cal_p_tensor(atoms_x,atoms_pos,atoms_batch,outs,outt)


        # 是否进行池化
        if self.summation:
            if atoms_batch is not None:
                out = scatter(src=out, index=atoms_batch, dim=0)
            else:
                out = torch.sum(input=out, dim=0)
        # 求偏导
        if self.grad=='polar':
            out=self.grad_polarzability(out.reshape(-1,3,3),atoms_pos)
        elif self.grad=='Hij':
            out=self.grad_hess_ij(energy=out,posj=posj,posi=posi)
        elif self.grad=='Hi':
            out=self.grad_hess_ii(energy=out,posa=posa,posb=posb)


        return out
if __name__ == "__main__":
    pass
