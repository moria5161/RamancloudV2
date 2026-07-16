
import numpy as np
np.random.seed(1)

from scipy.sparse import csc_matrix, eye, diags
from scipy.sparse.linalg import spsolve
import warnings
warnings.filterwarnings('ignore')

def WhittakerSmooth(x,w,lambda_,differences=1):
        '''
        Penalized least squares algorithm for background fitting

        input
            x: input data (i.e. chromatogram of spectrum)
            w: binary masks (value of the mask is zero if a point belongs to peaks and one otherwise)
            lambda_: parameter that can be adjusted by user. The larger lambda is,  the smoother the resulting background
            differences: integer indicating the order of the difference of penalties

        output
            the fitted background vector
        '''
        X=np.matrix(x)
        m=X.size
        i=np.arange(0,m)
        E=eye(m,format='csc')
        D=E[1:]-E[:-1] # numpy.diff() does not work with sparse matrix. This is a workaround.
        W=diags(w,0,shape=(m,m))
        A=csc_matrix(W+(lambda_*D.T*D))
        B=csc_matrix(W*X.T)
        background=spsolve(A,B)
        return np.array(background)

def ZhangFit(x, lambda_=100, porder=1, repitition=15):
    '''
    Implementation of Zhang fit for Adaptive iteratively reweighted penalized least squares for baseline fitting. Modified from Original implementation by Professor Zhimin Zhang at https://github.com/zmzhang/airPLS/
    
    lambda_: parameter that can be adjusted by user. The larger lambda is,  the smoother the resulting background, z

    porder: adaptive iteratively reweighted penalized least squares for baseline fitting

    repitition: how many iterations to run, and default value is 15.
    '''

    yorig=np.array(x)
    corrected=[]

    m=yorig.shape[0]
    w=np.ones(m)
    for i in range(1,repitition+1):
        corrected=WhittakerSmooth(yorig,w,lambda_, porder)
        d=yorig-corrected
        dssn=np.abs(d[d<0].sum())
        if(dssn<=0.001*(abs(yorig)).sum() or i==repitition):
            # if(i==repitition): print('WARING max iteration reached!')
            break
        w[d>=0]=0 # d>0 means that this point is part of a peak, so its weight is set to 0 in order to ignore it
        w[d<0]=np.exp(i*np.abs(d[d<0])/dssn)
        w[0]=np.exp(i*(d[d<0]).max()/dssn) 
        w[-1]=w[0]

    return yorig-corrected
        

def airpls_old(x, lambda_=100, order_=1):

    return ZhangFit(x, lambda_, order_)
     


# if __name__ == "__main__":
#     # Example usage
#     x = np.random.rand(100)  # Example data
#     lambda_ = 100
#     porder = 1
#     repitition = 15

#     baseline_corrected = ZhangFit(x, lambda_, porder, repitition)
#     print("Original Data:", x)
#     print("Baseline Corrected Data:", baseline_corrected)