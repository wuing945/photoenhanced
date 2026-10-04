"""Pixel frequency separation and feathered local editing, following the lesson."""
import math
import cv2
import numpy as np

LUMA=np.array([.2126,.7152,.0722],np.float32)

def blur(a,r):
    return cv2.GaussianBlur(a,(0,0),max(.3,float(r)),borderType=cv2.BORDER_REFLECT101)

def split(image,radius):
    low=blur(image,radius)
    # Apply Image: Subtract, scale 2, offset 128 (neutral 0.5 in float).
    high=.5+(image-low)*.5
    return low,high

def combine(low,high):
    # Linear Light; do not clip either component before reconstruction.
    return low+2*high-1

def regional_blur(low,mask,radius):
    # A feathered selection excludes hair, lips and neighboring dark features
    # from the sampling pool; change only pixels inside the selection.
    denominator=blur(mask,radius)
    if low.ndim==2:
        weighted=blur(low*mask,radius)
        return np.where(denominator>1e-5,weighted/np.maximum(denominator,1e-5),low)
    weighted=blur(low*mask[:,:,None],radius)
    return np.where((denominator>1e-5)[:,:,None],weighted/np.maximum(denominator[:,:,None],1e-5),low)

def repair_component(image,mask,radius):
    if not np.any(mask):return image.copy()
    # Navier-Stokes inpainting supports float32 single channels. Keep texture
    # residuals in float so the neutral gray texture layer is not quantized.
    return np.stack([cv2.inpaint(np.ascontiguousarray(image[:,:,c],dtype=np.float32),mask,float(radius),cv2.INPAINT_NS) for c in range(3)],axis=2)

def blemish_mask(image,skin,face_width,preserve_marks=True):
    lab=cv2.cvtColor(np.clip(image,0,1).astype(np.float32),cv2.COLOR_RGB2LAB)
    lab_base=blur(lab,max(2,face_width*.018))
    red=lab[:,:,1]-lab_base[:,:,1]
    dark=lab_base[:,:,0]-lab[:,:,0]
    bright=lab[:,:,0]-lab_base[:,:,0]
    # Local red/dark lesions and small raised bright centers; neutral dark
    # moles are excluded. This heuristic has a user-controlled repair brush
    # for spots it cannot safely classify.
    candidate=((red>1.8)&(dark>.5))|((bright>4)&(red>1))
    if not preserve_marks:candidate|=(dark>5)
    candidate=(candidate&(skin>.45)).astype(np.uint8)
    n,labels,stats,_=cv2.connectedComponentsWithStats(candidate,8)
    out=np.zeros(candidate.shape,np.uint8)
    max_diameter=max(6,int(face_width*.055))
    for k in range(1,n):
        _,_,cw,ch,area=stats[k]
        if 2<=area<=max_diameter**2*.6 and max(cw,ch)<=max_diameter:
            out[labels==k]=255
    out=cv2.dilate(out,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(max(3,int(face_width*.008))|1,)*2))
    out[skin<.2]=0
    return out

def face_regions(points,shape,skin):
    # Landmark-attached local selections: two cheeks, forehead, chin.
    fw=float(np.ptp(points[:,0]));fh=float(np.ptp(points[:,1]))
    yy,xx=np.mgrid[:shape[0],:shape[1]].astype(np.float32)
    horizontal=points[263]-points[33];horizontal/=max(np.linalg.norm(horizontal),1)
    vertical=np.array([-horizontal[1],horizontal[0]])
    if np.dot(points[152]-points[10],vertical)<0:vertical=-vertical
    zones=[(np.mean(points[[50,101,205]],axis=0),fw*.19,fh*.17),
           (np.mean(points[[280,330,425]],axis=0),fw*.19,fh*.17),
           ((points[10]+points[9])*.5,fw*.26,fh*.13),
           ((points[17]+points[152])*.5,fw*.19,fh*.10)]
    for center,rx,ry in zones:
        dx=xx-center[0];dy=yy-center[1]
        u=(dx*horizontal[0]+dy*horizontal[1])/max(rx,1)
        v=(dx*vertical[0]+dy*vertical[1])/max(ry,1)
        yield np.clip((1.15-u*u-v*v)/.4,0,1)*skin

def apply_brushes(image,strokes,settings,return_mask=False):
    h,w=image.shape[:2]
    split_radius=settings.separation_radius or max(2,min(w,h)*.0025)
    # Keep the same two layers for every stroke, as in the Photoshop lesson.
    # Re-splitting a reconstructed image between strokes would change texture.
    low,high=split(image,split_radius)
    sample_high=high.copy() if any(s.get('sample') is not None for s in strokes) else None
    union=np.zeros((h,w),np.float32)
    for stroke in strokes:
        mode=stroke.get('mode','smooth')
        raw=stroke.get('points',[])
        if not raw:continue
        if mode not in ('smooth','heal','heal_high','dodge','burn'):raise ValueError('�L�Ī�����')
        pts=np.asarray(raw,np.float32)
        if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)>10000 or not np.isfinite(pts).all():raise ValueError('�L�Ī�����y��')
        pts=np.clip(pts,0,1)*[w,h]
        radius=float(stroke.get('radius',.012))*min(w,h)
        amount=float(stroke.get('amount',.8))
        if not math.isfinite(radius) or not math.isfinite(amount):raise ValueError('�L�Ī�����Ѽ�')
        radius=max(1,min(min(w,h)*.2,radius));amount=max(0,min(1,amount))
        smooth_radius=settings.low_radius or max(split_radius*3,radius*.45)
        pad=int(max(radius*1.7,split_radius*4,smooth_radius*4))+5
        x0=max(0,int(pts[:,0].min())-pad);x1=min(w,int(pts[:,0].max())+pad+1)
        y0=max(0,int(pts[:,1].min())-pad);y1=min(h,int(pts[:,1].max())+pad+1)
        lo=low[y0:y1,x0:x1];hi=high[y0:y1,x0:x1]
        local_pts=np.round(pts-[x0,y0]).astype(np.int32)
        hard=np.zeros(lo.shape[:2],np.uint8)
        thick=max(1,round(radius*2))
        if len(local_pts)>1:cv2.polylines(hard,[local_pts],False,255,thick,cv2.LINE_AA)
        for p in (local_pts[0],local_pts[-1]):cv2.circle(hard,tuple(p),max(1,round(radius)),255,-1)
        mask=blur(hard.astype(np.float32)/255,max(1,radius*.2))
        union[y0:y1,x0:x1]=np.maximum(union[y0:y1,x0:x1],mask*amount)
        if mode=='smooth':
            target=regional_blur(lo,mask,smooth_radius)
            lo+=(target-lo)*(mask*amount)[:,:,None]
        elif mode in ('heal','heal_high'):
            sample=stroke.get('sample')
            if sample is not None:
                sample=np.asarray(sample,np.float32)
                if sample.shape!=(2,) or not np.isfinite(sample).all():raise ValueError('�L�Ī����ˮy��')
                offset=np.clip(sample,0,1)*[w,h]-pts[0]
                yy,xx=np.mgrid[y0:y1,x0:x1].astype(np.float32)
                healed=cv2.remap(sample_high,xx+float(offset[0]),yy+float(offset[1]),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT101)
            else:
                healed=repair_component(hi,hard,max(2,radius*.4))
            hi+=(healed-hi)*(mask*amount)[:,:,None]
            if mode=='heal':
                healed_low=repair_component(lo,hard,max(2,radius*.4))
                lo+=(healed_low-lo)*(mask*amount)[:,:,None]
        else:
            lo+=(mask*amount*.065*(1 if mode=='dodge' else -1))[:,:,None]
    out=np.clip(combine(low,high),0,1)
    return (out,union) if return_mask else out
