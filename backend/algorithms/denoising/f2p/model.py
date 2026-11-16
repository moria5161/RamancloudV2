import torch
from torch import nn


class PatchEmbedding(nn.Module):
    def __init__(self, patch_size, embed_dim):
        super().__init__()
        self.proj = nn.Conv1d(1, embed_dim, kernel_size=patch_size, stride=patch_size)

    def forward(self, x):
        return self.proj(x).transpose(1, 2)


class RelativeAttention(nn.Module):
    def __init__(self, dim, num_patches, heads=8):
        super().__init__()
        self.heads = heads
        self.scale = (dim // heads) ** -0.5
        self.to_qkv = nn.Linear(dim, dim * 3, bias=False)
        self.to_out = nn.Linear(dim, dim)
        self.relative_position_bias_table = nn.Parameter(torch.zeros(2 * num_patches - 1, heads))
        nn.init.trunc_normal_(self.relative_position_bias_table, std=.02)

        coords = torch.arange(num_patches)
        relative_coords = coords[None, :] - coords[:, None]
        relative_coords += num_patches - 1
        self.register_buffer('relative_position_index', relative_coords)

    def forward(self, x):
        _, num_patches, _ = x.shape
        qkv = self.to_qkv(x).chunk(3, dim=-1)
        q, k, v = (
            t.reshape(t.shape[0], t.shape[1], self.heads, -1).transpose(1, 2)
            for t in qkv
        )
        dots = (q @ k.transpose(-2, -1)) * self.scale
        bias = self.relative_position_bias_table[self.relative_position_index.reshape(-1)]
        bias = bias.reshape(num_patches, num_patches, -1).permute(2, 0, 1).contiguous()
        attn = (dots + bias.unsqueeze(0)).softmax(dim=-1)
        out = (attn @ v).transpose(1, 2).reshape(x.shape)
        return self.to_out(out)


class RPETransformerBlock(nn.Module):
    def __init__(self, dim, num_patches, heads):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = RelativeAttention(dim, num_patches, heads)
        self.norm2 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, dim * 4), nn.GELU(), nn.Linear(dim * 4, dim))

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        return x + self.ffn(self.norm2(x))


class Fast2PeakRPE(nn.Module):
    def __init__(self, spectrum_length, patch_size, embed_dim, depth, heads):
        super().__init__()
        if spectrum_length % patch_size != 0:
            raise ValueError('The spectral length must be divisible by the size of the patch')
        if embed_dim % heads != 0:
            raise ValueError('The embedding dimension must be divisible by the number of heads')
        self.num_patches = spectrum_length // patch_size
        self.patch_size = patch_size
        self.patch_embed = PatchEmbedding(patch_size, embed_dim)
        self.transformer_blocks = nn.ModuleList([
            RPETransformerBlock(embed_dim, self.num_patches, heads) for _ in range(depth)
        ])
        self.decoder = nn.Sequential(nn.Linear(embed_dim, embed_dim * 2), nn.GELU(), nn.Linear(embed_dim * 2, patch_size))

    def unpatchify(self, patches):
        batch_size, num_patches, patch_size = patches.shape
        return patches.reshape(batch_size, 1, num_patches * patch_size)

    def forward(self, x):
        patches = self.patch_embed(x)
        for block in self.transformer_blocks:
            patches = block(patches)
        return self.unpatchify(self.decoder(patches))
