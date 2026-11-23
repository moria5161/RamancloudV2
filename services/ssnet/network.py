from __future__ import print_function, division
import torch.nn as nn
import torch

# 可以学习的下采样卷积
class DownsampleBlock(nn.Module):
    def __init__(self, channels):
        super(DownsampleBlock, self).__init__()
        # 使用 kernel_size=3, stride=2 相比 kernel=2 增加了感受野重叠，防畸变
        self.down = nn.Sequential(
            nn.Conv1d(channels, channels, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm1d(channels),
            nn.ReLU(inplace=True) # 或者你刚学到的 Softplus
        )

    def forward(self, x):
        return self.down(x)

class ResMultiScaleConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super(ResMultiScaleConvBlock, self).__init__()
        
        # 恒等映射/残差捷径：若通道不一致则通过 1x1 卷积对齐
        self.shortcut = nn.Sequential()
        if in_ch != out_ch:
            self.shortcut = nn.Sequential(
                nn.Conv1d(in_ch, out_ch, kernel_size=1, bias=False),
                nn.BatchNorm1d(out_ch)
            )
        
        # 分支1：小感受野，捕捉尖锐的局部特征峰 (Kernel = 5, Dilation = 1)
        self.branch1 = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size=5, stride=1, padding=2, bias=False),
            nn.BatchNorm1d(out_ch),
            nn.ReLU(inplace=True)
        )
        
        # 分支2：中等感受野，利用空洞卷积提升效率 (Kernel = 5, Dilation = 3, 感受野=13)
        self.branch2 = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size=5, stride=1, padding=6, dilation=3, bias=False),
            nn.BatchNorm1d(out_ch),
            nn.ReLU(inplace=True)
        )
        
        # 分支3：宽感受野，捕捉波段整体基线趋势 (Kernel = 5, Dilation = 7, 感受野=29)
        self.branch3 = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size=5, stride=1, padding=14, dilation=7, bias=False),
            nn.BatchNorm1d(out_ch),
            nn.ReLU(inplace=True)
        )
        
        # 1x1 卷积融合 3 个分支的信息
        self.fusion = nn.Sequential(
            nn.Conv1d(out_ch * 3, out_ch, kernel_size=1, stride=1, bias=False),
            nn.BatchNorm1d(out_ch)
        )
        
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        residual = self.shortcut(x)
        
        x1 = self.branch1(x)
        x2 = self.branch2(x)
        x3 = self.branch3(x)
        
        # 拼接并融合
        out = torch.cat([x1, x2, x3], dim=1)
        out = self.fusion(out)
        
        # 引入残差相加
        out = self.relu(out + residual)
        return out


# 2. 升级版：高效通道注意力机制 (ECA-Net)
class ECALayer(nn.Module):
    def __init__(self, channel, k_size=3):
        super(ECALayer, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool1d(1)
        # 用 1D 卷积替代 SE-block 中的两个全连接层，避免维度惩罚，参数量极小
        self.conv = nn.Conv1d(1, 1, kernel_size=k_size, padding=(k_size - 1) // 2, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # 提取通道全局特征
        y = self.avg_pool(x)  # [B, C, 1]
        # 变换维度以适配 Conv1d: [B, C, 1] -> [B, 1, C]
        y = self.conv(y.transpose(-1, -2)).transpose(-1, -2)  # [B, C, 1]
        y = self.sigmoid(y)
        return x * y.expand_as(x)
    
class up_conv(nn.Module):
    def __init__(self, in_ch, out_ch, size):
        super(up_conv, self).__init__()
        self.up = nn.Sequential(
                nn.Upsample(size=size[0]),  # 使用明确的目标大小
                nn.Conv1d(in_ch, out_ch, kernel_size=9, stride=1, padding='same', bias=True),
                nn.BatchNorm1d(out_ch),
                nn.ReLU(inplace=True)
        )

    def forward(self, x):
        x = self.up(x)
        return x

# class up_conv(nn.Module):
#     def __init__(self, in_ch, out_ch):
#         super(up_conv, self).__init__()
#         self.conv = nn.Sequential(
#             nn.Conv1d(in_ch,out_ch,kernel_size=9,stride=1,padding='same',bias=True),
#             nn.BatchNorm1d(out_ch),
#             nn.ReLU(inplace=True)
#         )

#     def forward(self, x, target_size):
#         # 一次性直接恢复到 skip connection 的真实尺寸
#         x = F.interpolate(x,size=target_size,mode='linear',align_corners=False)
#         x = self.conv(x)
#         return x
class U_Net(nn.Module):
    def __init__(self, in_ch=1, out_ch=1, size=2500):
        super(U_Net, self).__init__()

        n1 = 16
        filters = [n1, n1 * 2, n1 * 4, n1 * 8, n1 * 16, n1 * 32]
        
        # 计算每一层的大小
        sizes = []
        current_size = size
        sizes.append([current_size])
        
        # 计算下采样每层的大小
        for i in range(5):  # 5次下采样
            current_size = current_size // 2
            sizes.append([current_size])
        
        # 
        
        self.Down1 = DownsampleBlock(filters[0])
        self.Down2 = DownsampleBlock(filters[1])
        self.Down3 = DownsampleBlock(filters[2])
        self.Down4 = DownsampleBlock(filters[3])
        self.Down5 = DownsampleBlock(filters[4])

        self.dropout = nn.Dropout(p=0.5)

        self.Conv1 = ResMultiScaleConvBlock(in_ch, filters[0])
        self.Conv2 = ResMultiScaleConvBlock(filters[0], filters[1])
        self.Conv3 = ResMultiScaleConvBlock(filters[1], filters[2])
        self.Conv4 = ResMultiScaleConvBlock(filters[2], filters[3])
        self.Conv5 = ResMultiScaleConvBlock(filters[3], filters[4])
        self.Conv6 = ResMultiScaleConvBlock(filters[4], filters[5])

        # 创建上采样块
        self.Up6 = up_conv(filters[5], filters[4], sizes[4])
        # self.Up_conv6 = conv_block(filters[5], filters[4])
        self.Up_conv6 = ResMultiScaleConvBlock(filters[5], filters[4])
        self.Se_Bk6 = ECALayer(filters[5])

        self.Up5 = up_conv(filters[4], filters[3], sizes[3])
        # self.Up_conv5 = conv_block(filters[4], filters[3])
        self.Up_conv5 = ResMultiScaleConvBlock(filters[4], filters[3])
        self.Se_Bk5 = ECALayer(filters[4])

        self.Up4 = up_conv(filters[3], filters[2], sizes[2])
        # self.Up_conv4 = conv_block(filters[3], filters[2])
        self.Up_conv4 = ResMultiScaleConvBlock(filters[3], filters[2])
        self.Se_Bk4 = ECALayer(filters[3])

        self.Up3 = up_conv(filters[2], filters[1], sizes[1])
        # self.Up_conv3 = conv_block(filters[2], filters[1])
        self.Up_conv3 = ResMultiScaleConvBlock(filters[2], filters[1])
        self.Se_Bk3 = ECALayer(filters[2])

        self.Up2 = up_conv(filters[1], filters[0], sizes[0])
        # self.Up_conv2 = conv_block(filters[1], filters[0])
        self.Up_conv2 = ResMultiScaleConvBlock(filters[1], filters[0])
        self.Se_Bk2 = ECALayer(filters[1])

        # self.Conv = nn.Conv1d(filters[0], out_ch, kernel_size=1, stride=1, padding='same')

        # 2026.6.24 最后输出层添加一个ReLU函数
        # self.Conv = nn.Sequential(
        # nn.Conv1d(filters[0], out_ch, kernel_size=1, stride=1, padding='same'),
        # nn.ReLU(inplace=True)
        # )

        # 2026.6.29 最后输出层添加一个sigmoid函数 ReLU函数太过于一刀切
        self.Conv = nn.Sequential(
            nn.Conv1d(filters[0], out_ch, kernel_size=1, stride=1, padding='same'),
            nn.Sigmoid()
        )


    def forward(self, x):
        e1 = self.Conv1(x)
        
        e2 = self.Down1(e1)
        e2 = self.Conv2(e2)
        
        e3 = self.Down2(e2)
        e3 = self.Conv3(e3)
        
        e4 = self.Down3(e3)
        e4 = self.Conv4(e4)
        
        e5 = self.Down4(e4)
        e5 = self.Conv5(e5)
        e5 = self.dropout(e5)
        
        e6 = self.Down5(e5)
        e6 = self.Conv6(e6)
        
        # 使用nn.functional.interpolate明确调整尺寸，确保上采样后的特征图尺寸与下采样阶段对应层的特征图尺寸匹配
        d6 = self.Up6(e6)
        
        # 确保d6的长度与e5相同
        if d6.shape[2] != e5.shape[2]:
            d6 = nn.functional.interpolate(d6, size=e5.shape[2])
            
        d6 = torch.cat((e5, d6), dim=1)
        d6 = self.Se_Bk6(d6)
        d6 = self.Up_conv6(d6)
        
        d5 = self.Up5(d6)
        # 确保d5的长度与e4相同
        if d5.shape[2] != e4.shape[2]:
            d5 = nn.functional.interpolate(d5, size=e4.shape[2])
            
        d5 = torch.cat((e4, d5), dim=1)
        d5 = self.Se_Bk5(d5)
        d5 = self.Up_conv5(d5)
        
        d4 = self.Up4(d5)
        # 确保d4的长度与e3相同
        if d4.shape[2] != e3.shape[2]:
            d4 = nn.functional.interpolate(d4, size=e3.shape[2])
            
        d4 = torch.cat((e3, d4), dim=1)
        d4 = self.Se_Bk4(d4)
        d4 = self.Up_conv4(d4)
        
        d3 = self.Up3(d4)
        # 确保d3的长度与e2相同
        if d3.shape[2] != e2.shape[2]:
            d3 = nn.functional.interpolate(d3, size=e2.shape[2])
        
        d3 = torch.cat((e2, d3), dim=1)
        d3 = self.Se_Bk3(d3)
        d3 = self.Up_conv3(d3)
        
        d2 = self.Up2(d3)
        # 确保d2的长度与e1相同
        if d2.shape[2] != e1.shape[2]:
            d2 = nn.functional.interpolate(d2, size=e1.shape[2])
        
        d2 = torch.cat((e1, d2), dim=1)
        d2 = self.Se_Bk2(d2)
        d2 = self.Up_conv2(d2)
        
        out = self.Conv(d2)
        
        return out

def Unet(size):
    return U_Net(1, 1, size)