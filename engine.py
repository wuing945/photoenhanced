"""Offline, source-pixel portrait retouching. No image generation or network calls."""
from __future__ import annotations
import io, json, math, time, os
from dataclasses import dataclass, asdict
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageCms
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parent/'work'/'matplotlib'))
os.environ.setdefault('MPLBACKEND','Agg')
import mediapipe as mp
from frequency import split,combine,regional_blur,repair_component,blemish_mask,face_regions,apply_brushes

ROOT = Path(__file__).resolve().parent
LUMA = np.array([.2126, .7152, .0722], np.float32)
OVAL = [10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109]
LEFT_EYE = [33,160,158,133,153,144]
RIGHT_EYE = [362,385,387,263,373,380]
LIPS = [61,40,37,0,267,270,291,321,314,17,84,91]
BROWS = [[70,63,105,66,107,55,65,52,53,46],[336,296,334,293,300,276,283,282,295,285]]
SUPPORTED = {'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}

@dataclass
class Settings:
    smoothing: float = .75
    lighting: float = .65
    color: float = .40
    detail: float = .20
    body: bool = True
    preserve_marks: bool = True
    format: str = 'jpg'
    blemish: float = .95
    separation_radius: float = 0
    low_radius: float = 0
    automatic: bool = True

    @classmethod
    def parse(cls, values=None):
        values=values or {}
        s=cls(**{k:v for k,v in values.items() if k in cls.__dataclass_fields__})
        for k in ['smoothing','lighting','color','detail','blemish']:
            v=float(getattr(s,k))
            if not math.isfinite(v): raise ValueError('�j�ץ����O�����ƭ�')
            setattr(s,k,max(0.,min(1.,v)))
        s.body=bool(s.body);s.preserve_marks=bool(s.preserve_marks)
        s.automatic=bool(s.automatic)
        for k in ['separation_radius','low_radius']:
            v=float(getattr(s,k))
            if not math.isfinite(v):raise ValueError('�ҽk�b�|�����O�����ƭ�')
            setattr(s,k,max(0,min(200,v)))
        if s.format not in ('jpg','png'): raise ValueError('���䴩����X�榡')
        return s

def gaussian(a,sigma):
    return cv2.GaussianBlur(a,(0,0),max(.15,float(sigma)),borderType=cv2.BORDER_REFLECT101)

def polygon(shape,points):
    m=np.zeros(shape,np.float32)
    cv2.fillPoly(m,[np.round(points).astype(np.int32)],1.)
    return m

def shrink_soft(mask,r):
    k=max(1,int(r))
    eroded=cv2.erode(mask,np.ones((k,k),np.uint8))
    return np.clip(gaussian(eroded,max(1,r*.7)),0,1)*mask

def load_photo(path):
    with Image.open(path) as src:
        # Camera JPEG/MPO may contain a thumbnail/depth/secondary exposure.
        # Frame 0 is the primary photograph; this is not an animated image.
        if getattr(src,'n_frames',1)>1 and src.format not in ('JPEG','MPO'):
            raise ValueError('�Шϥγ�i�R�A�Ӥ��F���B�z�h���ΰʵe��')
        src.seek(0)
        src.load()
        exif=src.getexif();profile=src.info.get('icc_profile')
        im=ImageOps.exif_transpose(src)
        alpha=im.getchannel('A') if 'A' in im.getbands() else None
        rgb=im.convert('RGB')
        note=''
        if profile:
            try:
                rgb=ImageCms.profileToProfile(rgb,ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGB')
            except Exception:
                note='��Ϧ�m�y�z�ɵL�kŪ���A�� sRGB �B�z�C'
        exif[274]=1
        exif[40962],exif[40963]=rgb.size
        return rgb,alpha,exif,note

class Retoucher:
    def __init__(self):
        cv2.setNumThreads(2)
        base=mp.tasks.BaseOptions
        vision=mp.tasks.vision
        self.faces=vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=base(model_asset_buffer=(ROOT/'models/face_landmarker.task').read_bytes()),
            num_faces=12,min_face_detection_confidence=.4,min_face_presence_confidence=.5))
        self.segmenter=vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=base(model_asset_buffer=(ROOT/'models/selfie_multiclass.tflite').read_bytes()),
            output_category_mask=False,output_confidence_masks=True))

    def close(self):
        self.faces.close();self.segmenter.close()

    def detect(self,rgb):
        h,w=rgb.shape[:2]
        scale=min(1.,1500/max(h,w))
        small=cv2.resize(rgb,(max(1,round(w*scale)),max(1,round(h*scale))))
        found=[]
        def run(view,offset=(0,0),size=None):
            sh,sw=view.shape[:2]
            result=self.faces.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.ascontiguousarray(view)))
            for face in result.face_landmarks:
                pts=np.array([[p.x*sw+offset[0],p.y*sh+offset[1]] for p in face],np.float32)/scale
                width=np.ptp(pts[OVAL,0]);height=np.ptp(pts[OVAL,1])
                if min(width,height)<30: continue
                center=pts[OVAL].mean(axis=0)
                if any(np.linalg.norm(center-p[OVAL].mean(axis=0)) < max(width,np.ptp(p[OVAL,0]))*.4 for p in found): continue
                found.append(pts)
        run(small)
        # Overlapping tiles recover small faces in wider group photographs.
        if min(small.shape[:2])>=400:
            th,tw=small.shape[:2]
            tilew,tileh=round(tw*.65),round(th*.75)
            for ox,oy in [(0,0),(tw-tilew,0),(0,th-tileh),(tw-tilew,th-tileh)]:
                run(small[oy:oy+tileh,ox:ox+tilew],(ox,oy))
        return sorted(found,key=lambda p:float(np.ptp(p[OVAL,0])),reverse=True)[:12]

    def segment(self,rgb):
        h,w=rgb.shape[:2]
        scale=min(1.,1400/max(h,w))
        small=cv2.resize(rgb,(round(w*scale),round(h*scale)))
        result=self.segmenter.segment(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.ascontiguousarray(small)))
        body=result.confidence_masks[2].numpy_view().copy()
        face=result.confidence_masks[3].numpy_view().copy()
        return cv2.resize(body,(w,h)),cv2.resize(face,(w,h))

    def process(self,path,outdir,settings=None,progress=lambda x:None,edits=None):
        started=time.time();s=Settings.parse(settings)
        progress('Ū�����')
        im,alpha,exif,note=load_photo(path)
        rgb=np.asarray(im);h,w=rgb.shape[:2]
        progress('�w��H�y�P���x')
        faces=self.detect(rgb)
        if not faces and not edits:
            return {'status':'skipped','name':Path(path).name,'message':'��������i�ΤH�y�F�i�Ρu�����׹ϡv�e�X�d���B�z�C','width':w,'height':h,'faces':0}
        progress('�إߥֽ��P���x�O�@�B�n')
        body_prob,face_prob=self.segment(rgb)
        a=rgb.astype(np.float32)/255
        face_union=np.zeros((h,w),np.float32)
        edit_union=np.zeros((h,w),np.float32)
        regions=[]
        for pts in faces:
            fw=float(np.ptp(pts[OVAL,0]));pad=int(fw*.15)+8
            x0=max(0,int(pts[OVAL,0].min())-pad);x1=min(w,int(pts[OVAL,0].max())+pad)
            y0=max(0,int(pts[OVAL,1].min())-pad);y1=min(h,int(pts[OVAL,1].max())+pad)
            pp=pts-[x0,y0];shape=(y1-y0,x1-x0)
            outer=polygon(shape,pp[OVAL]);outer=shrink_soft(outer,max(2,fw*.018))
            feature=np.zeros(shape,np.float32)
            for ids in [LEFT_EYE,RIGHT_EYE,LIPS,*BROWS]:
                feature=np.maximum(feature,polygon(shape,cv2.convexHull(pp[ids].astype(np.float32))))
            nose=pp[[98,97,2,326,327]]
            feature=np.maximum(feature,polygon(shape,cv2.convexHull(nose.astype(np.float32))))
            k=max(3,int(fw*.025));feature=cv2.dilate(feature,np.ones((k,k),np.uint8))
            feature=np.clip(gaussian(feature,fw*.008),0,1)
            prob=face_prob[y0:y1,x0:x1]
            skin=outer*np.clip((prob-.2)/.55,0,1)
            local=a[y0:y1,x0:x1]
            l=local@LUMA
            # Neutral dark marks are protected; red blemishes remain editable.
            residual=gaussian(l,max(1,fw*.009))-l
            lab=cv2.cvtColor(local,cv2.COLOR_RGB2LAB)
            red_delta=lab[:,:,1]-gaussian(lab[:,:,1],max(2,fw*.018))
            marks=((residual>.035)&(red_delta<1.8)).astype(np.float32) if s.preserve_marks else np.zeros(shape,np.float32)
            glitter=((l-gaussian(l,max(1,fw*.015)))>.065).astype(np.float32)
            protection=cv2.dilate(np.maximum(marks,glitter),np.ones((max(3,int(fw*.008)),)*2,np.uint8))
            protection=np.clip(gaussian(protection,max(1,fw*.004)),0,1)
            mask=skin*(1-feature)*(1-protection)
            face_union[y0:y1,x0:x1]=np.maximum(face_union[y0:y1,x0:x1],skin)
            if s.automatic:edit_union[y0:y1,x0:x1]=np.maximum(edit_union[y0:y1,x0:x1],mask)
            regions.append((x0,y0,x1,y1,fw,skin,mask,feature,pp))
        body=np.clip((body_prob-.45)/.4,0,1)*(1-face_union) if s.body else np.zeros((h,w),np.float32)
        body=shrink_soft(body,max(2,min(w,h)*.002))
        progress('�ե�����P��������')
        # Balance broad body-skin light and shade in both directions.
        if s.automatic and s.body and s.lighting>0:
            luminance=a@LUMA
            field=regional_blur(luminance,body,max(3,min(w,h)*.035))
            delta=np.clip(field-luminance,-.07,.10)*body*s.lighting*.45
            a=np.clip(a+delta[:,:,None],0,1)
        for x0,y0,x1,y1,fw,skin,mask,feature,pp in regions:
            if not s.automatic:continue
            v=a[y0:y1,x0:x1].copy();l=v@LUMA
            progress('�������C�W�A��������C�W��m�P���t')
            radius=s.separation_radius or max(2,fw*.012)
            low,high=split(v,radius)
            if s.blemish>0:
                spots=blemish_mask(v,skin*(1-feature),fw,s.preserve_marks)
                if np.any(spots):
                    soft=np.clip(gaussian(spots.astype(np.float32)/255,max(1,fw*.002)),0,1)
                    healed_high=repair_component(high,spots,max(2,fw*.006))
                    healed_low=repair_component(low,spots,max(2,fw*.008))
                    high+=(healed_high-high)*(soft*s.blemish)[:,:,None]
                    low+=(healed_low-low)*(soft*s.blemish)[:,:,None]
            smooth_radius=s.low_radius or max(radius*3,fw*.05)
            for zone in face_regions(pp,skin.shape,mask):
                target=regional_blur(low,zone,smooth_radius)
                # Unlike the previous code, this changes brightness as well
                # as chroma. High-frequency pores remain in a separate layer.
                low+=(target-low)*(zone*s.smoothing)[:,:,None]
            local_lum=low@LUMA
            field=regional_blur(local_lum,mask,max(2,fw*.22))
            valid=mask>.4
            anchor=float(np.median(local_lum[valid])) if np.any(valid) else float(np.median(local_lum))
            difference=.65*(field-local_lum)+.35*(anchor-local_lum)
            adjustment=np.clip(difference,-.09,.14)*mask*s.lighting*.65
            low+=adjustment[:,:,None]
            # Chroma-only correction of local color blotches; no fixed skin color.
            lum=low@LUMA;ch=low-lum[:,:,None]
            ch_target=regional_blur(ch,mask,max(2,fw*.055))
            low+=np.clip(ch_target-ch,-.025,.025)*(mask*s.color*.55)[:,:,None]
            v=np.clip(combine(low,high),0,1)
            # Modest sharpening on facial details, avoiding skin texture halos.
            sharp=v-gaussian(v,max(.5,fw*.0017))
            v+=sharp*(feature*s.detail*.45)[:,:,None]
            a[y0:y1,x0:x1]=np.clip(v,0,1)
        if edits:
            progress('�M�ΧC�W��ϻP���W�״_����')
            a,manual_mask=apply_brushes(a,edits,s,return_mask=True)
            edit_union=np.maximum(edit_union,manual_mask)
        progress('�x�s��ѪR�צ��~�P���')
        out=Image.fromarray(np.uint8(np.round(np.clip(a,0,1)*255)))
        outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
        stamp=time.strftime('%Y%m%d_%H%M%S')+'_'+str(time.time_ns()%1000000).zfill(6)
        stem=Path(path).stem+'_'+stamp
        dest=outdir/(stem+'_retouched.'+s.format)
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        kwargs={'icc_profile':profile,'exif':exif.tobytes()}
        if s.format=='jpg':kwargs.update(quality=98,subsampling=0)
        elif alpha is not None:out.putalpha(alpha)
        out.save(dest,**kwargs)
        preview=out.convert('RGB');preview.thumbnail((1500,1500));preview.save(outdir/(stem+'_preview.jpg'),quality=94)
        before=im.copy();before.thumbnail((1500,1500));before.save(outdir/(stem+'_before.jpg'),quality=94)
        overlay=np.asarray(before).copy().astype(np.float32)
        mask_small=cv2.resize(edit_union,(before.width,before.height))
        overlay=overlay*(1-mask_small[:,:,None]*.4)+np.array([50,225,180])*mask_small[:,:,None]*.4
        Image.fromarray(np.uint8(overlay)).save(outdir/(stem+'_mask.jpg'),quality=94)
        comparisons=[]
        for i,(x0,y0,x1,y1,*_) in enumerate(regions):
            b=im.crop((x0,y0,x1,y1));c=out.convert('RGB').crop((x0,y0,x1,y1))
            pair=Image.new('RGB',(b.width*2,b.height));pair.paste(b,(0,0));pair.paste(c,(b.width,0))
            name=f'{stem}_face{i+1}_100percent.png';pair.save(outdir/name);comparisons.append(name)
        result={'status':'done','name':Path(path).name,'output':dest.name,'preview':stem+'_preview.jpg',
                'before':stem+'_before.jpg','mask':stem+'_mask.jpg','comparisons':comparisons,
                'faces':len(faces),'width':w,'height':h,'seconds':round(time.time()-started,2),
                'message':note or '�����A�w�O�d��ѪR�סC','settings':asdict(s)}
        (outdir/(stem+'_report.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
