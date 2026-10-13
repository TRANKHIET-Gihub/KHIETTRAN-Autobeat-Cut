import os, sys, math, shutil, subprocess, tempfile
from pathlib import Path
from dataclasses import dataclass
try:
    import cv2
except Exception:
    cv2 = None
from PySide6.QtCore import Qt, QUrl, QThread, Signal, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import *
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from autobeat_core import ExportSettings, RESOLUTIONS, build_encode_args, detect_beats, validate_output
from autobeat_ai import analyze_video_filters, trim_source_range

GENRES = {
 "Wedding / Cưới": ("Chậm","16:9","story"),
 "Portrait / Chân dung": ("Trung bình","4:5","story"),
 "Social / TikTok-Reels": ("Nhanh","9:16","energy"),
 "Travel / Du lịch": ("Trung bình","16:9","energy"),
 "Commercial / Quảng cáo": ("Nhanh","16:9","energy"),
 "Cinematic / Điện ảnh": ("Chậm","16:9","story")}
PACING = {"Rất nhanh":0.7,"Nhanh":1.2,"Trung bình":2.0,"Chậm":3.2,"Rất chậm":4.8}
def exe(name):
 candidates = [name, name + ".exe"] if os.name == "nt" else [name]
 roots = [Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)), Path(sys.executable).resolve().parent]
 for root in roots:
  for candidate in candidates:
   path = root / "tools" / candidate
   if path.is_file(): return str(path)
 return shutil.which(name)
def duration(path):
 if not exe("ffprobe"): return 0.0
 try:
  return float(subprocess.check_output([exe("ffprobe"),"-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",path],stderr=subprocess.DEVNULL).decode().strip())
 except: return 0.0
def thumbnail(path, sec=0.5, width=220):
 if cv2 is None: return QPixmap()
 cap=cv2.VideoCapture(path); cap.set(cv2.CAP_PROP_POS_MSEC,sec*1000); ok,fr=cap.read(); cap.release()
 if not ok:return QPixmap()
 h,w=fr.shape[:2]; fr=cv2.resize(fr,(width,max(1,int(h*width/w)))); fr=cv2.cvtColor(fr,cv2.COLOR_BGR2RGB)
 return QPixmap.fromImage(QImage(fr.data,fr.shape[1],fr.shape[0],fr.strides[0],QImage.Format_RGB888).copy())
@dataclass
class Clip:
 path:str; name:str; dur:float; score:float=0.0; notes:str="Chưa phân tích"
def inspect(path, dur):
 if cv2 is None:return .4,"Thiếu OpenCV",[]
 cap=cv2.VideoCapture(path); fps=cap.get(cv2.CAP_PROP_FPS) or 25
 total=cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0; dur=dur or total/fps
 step=max(1,int(fps*.7)); prev=None; prevgray=None; cuts=[0.0]; br=[]; sharp=[]; motion=[]
 i=0
 while True:
  ok,fr=cap.read()
  if not ok:break
  if i%step==0:
   sm=cv2.resize(fr,(128,72)); hsv=cv2.cvtColor(sm,cv2.COLOR_BGR2HSV)
   hist=cv2.calcHist([hsv],[0,1],None,[24,16],[0,180,0,256]); cv2.normalize(hist,hist)
   gray=cv2.cvtColor(sm,cv2.COLOR_BGR2GRAY); br.append(gray.mean()/255); sharp.append(min(1,cv2.Laplacian(gray,cv2.CV_64F).var()/500))
   if prev is not None:
    if cv2.compareHist(prev,hist,cv2.HISTCMP_BHATTACHARYYA)>.48:cuts.append(i/fps)
    motion.append(cv2.absdiff(gray,prevgray).mean()/50)
   prev,prevgray=hist,gray
  i+=1
 cap.release()
 b=sum(br)/max(1,len(br)); s=sum(sharp)/max(1,len(sharp)); m=sum(motion)/max(1,len(motion))
 score=max(0,min(1,.35*s+.25*(1-abs(b-.52))+.2*min(1,m)+.2))
 notes=("Sáng tốt" if .28<=b<=.82 else ("Khá tối" if b<.28 else "Dễ cháy sáng"))+" • "+("Chi tiết rõ" if s>.35 else "Độ nét vừa/thấp")+f" • {len(cuts)-1} điểm chuyển cảnh"
 if m>.35:notes+=" • Chuyển động nhiều"
 return score,notes,cuts
class AnalysisWorker(QThread):
 progress=Signal(int,str); done=Signal(list); fail=Signal(str)
 def __init__(self,clips):super().__init__();self.clips=clips
 def run(self):
  try:
   out=[]
   for i,c in enumerate(self.clips):
    s,n,cuts=inspect(c.path,c.dur);out.append((c.path,s,n,cuts))
    self.progress.emit(int((i+1)*100/len(self.clips)),f"Phân tích {i+1}/{len(self.clips)}")
   self.done.emit(out)
  except Exception as e:self.fail.emit(str(e))
class Renderer(QThread):
 progress=Signal(int,str); done=Signal(str); fail=Signal(str)
 def __init__(self,segments,music,out,settings,genre,usemusic,fade,lut_path=None,auto_light=False,auto_color=False,auto_wb=False):
  super().__init__();self.segments=segments;self.music=music;self.out=out;self.settings=settings;self.ratio=settings.ratio;self.genre=genre;self.usemusic=usemusic;self.fade=fade;self.lut_path=lut_path;self.auto_light=auto_light;self.auto_color=auto_color;self.auto_wb=auto_wb;self.cancel_requested=False;self.process=None
 def cancel(self):
  self.cancel_requested=True
  if self.process and self.process.poll() is None:
   try: self.process.terminate()
   except OSError: pass
 def _run(self,cmd):
  self.process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace")
  _,err=self.process.communicate()
  code=self.process.returncode
  self.process=None
  if self.cancel_requested: raise RuntimeError("Render đã bị hủy bởi người dùng.")
  if code: raise RuntimeError((err or "FFmpeg failed")[-1800:])
 def run(self):
  ff=exe("ffmpeg")
  if not ff:self.fail.emit("Không tìm thấy FFmpeg trong PATH.");return
  tmp=tempfile.mkdtemp(prefix="autobeat_");parts=[];color_cache={}
  try:
   for i,(path,a,b) in enumerate(self.segments):
    if self.cancel_requested: raise RuntimeError("Render đã bị hủy bởi người dùng.")
    if path not in color_cache:
     color_cache[path]=analyze_video_filters(path,self.auto_light,self.auto_color,self.auto_wb)
    vf_args=build_encode_args(self.settings,self.genre,lut_path=self.lut_path,extra_filters=color_cache[path])
    part=os.path.join(tmp,f"p{i:04}.mp4")
    cmd=[ff,"-y","-ss",str(a),"-i",path,"-t",str(b-a),"-an",*vf_args,"-preset","veryfast",part]
    self._run(cmd)
    parts.append(part);self.progress.emit(int((i+1)*75/len(self.segments)),f"Chuẩn hóa clip {i+1}/{len(self.segments)}")
   txt=os.path.join(tmp,"concat.txt")
   with open(txt,"w",encoding="utf-8") as f:
    for p in parts:f.write("file '"+p.replace("\\","/").replace("'","'\\''")+"'\n")
   joined=os.path.join(tmp,"joined.mp4")
   if self.cancel_requested: raise RuntimeError("Render đã bị hủy bởi người dùng.")
   self._run([ff,"-y","-f","concat","-safe","0","-i",txt,"-c","copy",joined])
   if self.cancel_requested: raise RuntimeError("Render đã bị hủy bởi người dùng.")
   if self.usemusic and self.music:
    cmd=[ff,"-y","-i",joined,"-stream_loop","-1","-i",self.music,"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a",f"{self.settings.audio_bitrate_kbps}k","-shortest"]
    if self.fade:cmd += ["-af","afade=t=in:st=0:d=1.2,volume=0.85"]
    cmd += ["-movflags","+faststart",self.out]
   else:cmd=[ff,"-y","-i",joined,"-c","copy","-movflags","+faststart",self.out]
   self._run(cmd)
   if self.cancel_requested: raise RuntimeError("Render đã bị hủy bởi người dùng.")
   mismatches=validate_output(self.out,self.settings)
   if mismatches: raise RuntimeError("Kiểm tra đầu ra không đạt:\n"+"\n".join(mismatches))
   self.progress.emit(100,"Render hoàn tất và đã kiểm tra metadata");self.done.emit(self.out)
  except Exception as e:self.fail.emit(str(e))
  finally:shutil.rmtree(tmp,ignore_errors=True)
class Window(QMainWindow):
 def __init__(self):
  super().__init__();self.setWindowTitle("KHIETTRAN Autobeat Cut");self.resize(1450,900);self.sources=[];self.music="";self.worker=None;self.aw=None
  root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root)
  head=QHBoxLayout();title=QLabel("KHIETTRAN <span style='color:#58d6bd'>AUTOBEAT CUT</span>");title.setTextFormat(Qt.RichText);title.setStyleSheet("font-size:22px;font-weight:bold")
  head.addWidget(title);head.addStretch();self.genre=QComboBox();self.genre.addItems(GENRES);self.pace=QComboBox();self.pace.addItems(PACING);self.ratio=QComboBox();self.ratio.addItems(["16:9","9:16","4:5","1:1"])
  for label,w in [("Thể loại",self.genre),("Nhịp dựng",self.pace),("Tỷ lệ",self.ratio)]:head.addWidget(QLabel(label));head.addWidget(w)
  outer.addLayout(head);split=QSplitter(Qt.Horizontal);outer.addWidget(split,1)
  left=QWidget();ll=QVBoxLayout(left);gb=QGroupBox("01 SOURCE MEDIA — AI SCENE ANALYSIS");gl=QVBoxLayout(gb);bar=QHBoxLayout()
  self.importbtn=QPushButton("＋ Import video");self.analyzebtn=QPushButton("✦ AI phân tích");self.view=QComboBox();self.view.addItems(["Extra large","Medium","Small"])
  for x in [self.importbtn,self.analyzebtn,QLabel("View"),self.view]:bar.addWidget(x)
  gl.addLayout(bar);self.list=QListWidget();self.list.setViewMode(QListWidget.IconMode);self.list.setResizeMode(QListWidget.Adjust);self.list.setMovement(QListWidget.Static);self.list.setWordWrap(True);self.list.setIconSize(QSize(180,110));gl.addWidget(self.list,1)
  pg=QGroupBox("Source Preview");pl=QVBoxLayout(pg);self.video=QVideoWidget();self.video.setMinimumHeight(200);pl.addWidget(self.video,1);self.previewlabel=QLabel("Chọn source để xem trước");pl.addWidget(self.previewlabel)
  row=QHBoxLayout();self.play=QPushButton("▶ Play/Pause");self.seek=QSlider(Qt.Horizontal);row.addWidget(self.play);row.addWidget(self.seek);pl.addLayout(row)
  self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio);self.player.setVideoOutput(self.video)
  ll.addWidget(gb,3);ll.addWidget(pg,2);split.addWidget(left)
  right=QWidget();rl=QVBoxLayout(right);mg=QGroupBox("02 MUSIC & EDIT PLAN");ml=QHBoxLayout(mg);self.musicbtn=QPushButton("♫ Chọn nhạc");self.musiclabel=QLabel("Chưa chọn nhạc");self.musiccheck=QCheckBox("Dùng nhạc nền");self.musiccheck.setChecked(True);self.beat=QPushButton("Phân tích BPM (beta)")
  for x in [self.musicbtn,self.musiclabel,self.musiccheck,self.beat]:ml.addWidget(x)
  rl.addWidget(mg)
  tg=QGroupBox("04 TIMELINE — CLIP / TRIM / ORDER");tl=QVBoxLayout(tg);tools=QHBoxLayout();self.auto=QPushButton("✦ Auto Assemble");self.add=QPushButton("＋ Thêm");self.remove=QPushButton("− Xóa");self.up=QPushButton("↑");self.down=QPushButton("↓");self.apply=QPushButton("Áp dụng Trim")
  for x in [self.auto,self.add,self.remove,self.up,self.down,self.apply]:tools.addWidget(x)
  tl.addLayout(tools);self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(["#","Clip","In (s)","Out (s)","Độ dài (s)","AI notes"]);self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch);self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);tl.addWidget(self.table,1)
  aud=QHBoxLayout();self.audiolabel=QLabel("AUDIO TIMELINE — chưa có nhạc");self.audioseek=QSlider(Qt.Horizontal);self.audioplay=QPushButton("▶ Preview audio")
  aud.addWidget(self.audiolabel,2);aud.addWidget(self.audioseek,2);aud.addWidget(self.audioplay);tl.addLayout(aud);rl.addWidget(tg,1)
  eg=QGroupBox("05 RENDER & EXPORT");el=QGridLayout(eg);self.output=QLineEdit(os.path.join(os.path.expanduser("~"),"Desktop","KHIETTRAN_Autobeat_Cut.mp4"));self.outputbtn=QPushButton("Chọn nơi lưu");self.fade=QCheckBox("Fade nhạc đầu");self.renderbtn=QPushButton("▶ RENDER VIDEO");self.cancelbtn=QPushButton("Hủy render");self.cancelbtn.setEnabled(False)
  self.lutpath=QLineEdit();self.lutpath.setPlaceholderText("Không dùng LUT / No LUT");self.lutbtn=QPushButton("Chọn LUT .cube");self.resolution=QComboBox();self.resolution.addItems(["Full HD","2K","4K","6K","8K"]);self.container=QComboBox();self.container.addItems(["MP4","MOV"]);self.codec=QComboBox();self.codec.addItems(["H.264","H.265"]);self.fps=QComboBox();self.fps.addItems(["25","30","60","120"]);self.bitrate=QComboBox();self.bitrate.addItems(["50 Mbps","100 Mbps","150 Mbps","200 Mbps","300 Mbps"]);self.language=QComboBox();self.language.addItems(["Tiếng Việt","English"]);self.language.setCurrentText("Tiếng Việt")
  self.auto_light=QCheckBox("Tự động ánh sáng (AI hỗ trợ)");self.auto_color=QCheckBox("Tự động màu sắc (AI hỗ trợ)");self.auto_wb=QCheckBox("Tự động cân bằng trắng (AI hỗ trợ)");self.trim_edges=QCheckBox("Tự động bỏ 2 giây đầu/cuối mỗi video nguồn");self.auto_light.setChecked(True);self.auto_color.setChecked(True);self.auto_wb.setChecked(True)
  el.addWidget(QLabel("Độ phân giải"),0,0);el.addWidget(self.resolution,0,1);el.addWidget(QLabel("Container"),0,2);el.addWidget(self.container,0,3);el.addWidget(QLabel("Codec"),0,4);el.addWidget(self.codec,0,5)
  el.addWidget(QLabel("FPS"),1,0);el.addWidget(self.fps,1,1);el.addWidget(QLabel("Bitrate video"),1,2);el.addWidget(self.bitrate,1,3);el.addWidget(QLabel("Language"),1,4);el.addWidget(self.language,1,5)
  el.addWidget(QLabel("Output"),2,0);el.addWidget(self.output,2,1,1,3);el.addWidget(self.outputbtn,2,4);el.addWidget(QLabel("LUT màu"),3,0);el.addWidget(self.lutpath,3,1,1,3);el.addWidget(self.lutbtn,3,4);el.addWidget(self.auto_light,4,0,1,2);el.addWidget(self.auto_color,4,2,1,2);el.addWidget(self.auto_wb,5,0,1,2);el.addWidget(self.trim_edges,5,2,1,4);el.addWidget(self.fade,6,0);el.addWidget(self.renderbtn,6,1,1,2);el.addWidget(self.cancelbtn,6,3,1,2)
  rl.addWidget(eg);self.progress=QProgressBar();self.status=QLabel("Sẵn sàng — phân tích cảnh bằng thị giác máy tính cục bộ.");rl.addWidget(self.progress);rl.addWidget(self.status);split.addWidget(right);split.setSizes([460,980])
  self.setStyleSheet("""QMainWindow,QWidget{background:#171b22;color:#e7edf4;font-size:12px}QGroupBox{border:1px solid #384351;border-radius:8px;margin-top:10px;padding:10px;font-weight:bold}QGroupBox::title{left:10px;padding:0 5px;color:#58d6bd}QPushButton{background:#293341;border:1px solid #465466;padding:8px;border-radius:5px}QPushButton:hover{background:#354458}QComboBox,QLineEdit{background:#222a35;border:1px solid #465466;padding:6px}QListWidget,QTableWidget{background:#11161d;border:1px solid #303b49}QHeaderView::section{background:#283240;padding:6px}QProgressBar{border:1px solid #394554;text-align:center}QProgressBar::chunk{background:#26b99a}""")
  self.importbtn.clicked.connect(self.import_videos);self.analyzebtn.clicked.connect(self.analyze);self.view.currentTextChanged.connect(self.refresh);self.list.currentRowChanged.connect(self.select_source);self.play.clicked.connect(self.toggle_play);self.player.positionChanged.connect(lambda p:self.seek.setValue(int(p*1000/max(1,self.player.duration()))));self.seek.sliderMoved.connect(lambda v:self.player.setPosition(int(self.player.duration()*v/1000)))
  self.musicbtn.clicked.connect(self.choose_music);self.audioplay.clicked.connect(self.preview_audio);self.audioseek.sliderMoved.connect(lambda v:self.player.setPosition(int(self.player.duration()*v/1000)));self.beat.clicked.connect(self.beat_analysis)
  self.genre.currentTextChanged.connect(self.set_genre);self.auto.clicked.connect(self.auto_assemble);self.add.clicked.connect(self.add_selected);self.remove.clicked.connect(self.remove_row);self.up.clicked.connect(lambda:self.move(-1));self.down.clicked.connect(lambda:self.move(1));self.apply.clicked.connect(self.apply_trim);self.outputbtn.clicked.connect(self.choose_output);self.lutbtn.clicked.connect(self.choose_lut);self.renderbtn.clicked.connect(self.render);self.cancelbtn.clicked.connect(self.cancel_render);self.container.currentTextChanged.connect(self.update_output_extension);self.language.currentTextChanged.connect(self.set_language);self.set_language("English");self.set_language(self.language.currentText())
 def refresh(self,*args):
  dims={"Extra large":(180,110),"Medium":(120,74),"Small":(72,45),"Rất lớn":(180,110),"Trung bình":(120,74),"Nhỏ":(72,45)}[self.view.currentText()];self.list.clear();self.list.setIconSize(QSize(*dims));self.list.setGridSize(QSize(dims[0]+28,dims[1]+58))
  for c in self.sources:
   it=QListWidgetItem(f"{c.name}\n{c.dur:.1f}s • {c.notes}");pix=thumbnail(c.path,min(.5,c.dur/4 if c.dur else .5),dims[0])
   if not pix.isNull():it.setIcon(pix)
   it.setData(Qt.UserRole,c.path);it.setTextAlignment(Qt.AlignHCenter);self.list.addItem(it)
 def import_videos(self):
  paths,_=QFileDialog.getOpenFileNames(self,"Import video","","Videos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)")
  known={c.path for c in self.sources}
  for p in paths:
   if p not in known:self.sources.append(Clip(p,Path(p).name,duration(p)))
  self.refresh();self.status.setText(f"Đã import {len(paths)} video.")
 def select_source(self,row):
  if 0<=row<len(self.sources):
   c=self.sources[row];self.previewlabel.setText(f"{c.name} | {c.dur:.2f}s | Score {c.score:.2f} | {c.notes}");self.player.setSource(QUrl.fromLocalFile(c.path))
 def toggle_play(self):
  self.player.pause() if self.player.playbackState()==QMediaPlayer.PlayingState else self.player.play()
 def analyze(self):
  if not self.sources:return
  self.analyzebtn.setEnabled(False);self.aw=AnalysisWorker(self.sources);self.aw.progress.connect(lambda p,m:(self.progress.setValue(p),self.status.setText(m)));self.aw.done.connect(self.analysis_done);self.aw.fail.connect(self.analysis_fail);self.aw.start()
 def analysis_done(self,results):
  by={p:(s,n) for p,s,n,cuts in results}
  for c in self.sources:c.score,c.notes=by.get(c.path,(c.score,c.notes))
  self.refresh();self.analyzebtn.setEnabled(True);self.status.setText("Phân tích xong. Score/notes là heuristic thị giác, không phải nhận diện ngữ nghĩa đầy đủ.")
 def analysis_fail(self,msg):self.analyzebtn.setEnabled(True);QMessageBox.warning(self,"Phân tích",msg)
 def choose_music(self):
  p,_=QFileDialog.getOpenFileName(self,"Chọn nhạc","","Audio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg)")
  if p:self.music=p;self.musiclabel.setText(Path(p).name);self.audiolabel.setText("AUDIO TIMELINE — "+Path(p).name)
 def preview_audio(self):
  if not self.music:QMessageBox.information(self,"Audio","Hãy chọn nhạc trước.");return
  self.player.setSource(QUrl.fromLocalFile(self.music));self.player.play()
 def beat_analysis(self):
  if not self.music:QMessageBox.information(self,"Beat","Hãy chọn nhạc trước.");return
  try:
   tempo,beats=detect_beats(self.music)
   QMessageBox.information(self,"BPM / Beat",f"Tempo ước tính: {tempo:.1f} BPM\nBeat đầu: {[round(float(x),2) for x in beats[:25]]}\n\nĐây là ước lượng tự động; cần nghe kiểm tra với nhạc có nhịp phức tạp.")
  except Exception as e:QMessageBox.warning(self,"BPM","Cài librosa trong requirements.txt để dùng.\n"+str(e))
 def set_genre(self,g):
  if g in GENRES:self.pace.setCurrentText(GENRES[g][0]);self.ratio.setCurrentText(GENRES[g][1])
 def add_segment(self,c,a,b):
  r=self.table.rowCount();self.table.insertRow(r);vals=[str(r+1),c.name,f"{a:.2f}",f"{b:.2f}",f"{b-a:.2f}",c.notes]
  for col,v in enumerate(vals):
   it=QTableWidgetItem(v)
   if col in (0,1,4,5):it.setFlags(it.flags()&~Qt.ItemIsEditable)
   self.table.setItem(r,col,it)
  self.table.item(r,1).setData(Qt.UserRole,c.path)
 def auto_assemble(self):
  if not self.sources:return
  genre=self.genre.currentText();trim=2.0 if self.trim_edges.isChecked() else 0.0;items=[c for c in self.sources if c.dur>2*trim+0.1]
  if GENRES[genre][2]=="energy":items.sort(key=lambda c:c.score,reverse=True)
  self.table.setRowCount(0);step=PACING[self.pace.currentText()]
  for c in items:
   try:start,limit=trim_source_range(c.dur,self.trim_edges.isChecked())
   except ValueError:continue
   while start<limit-.1:
    end=min(limit,start+step);self.add_segment(c,start,end);start=end
  self.status.setText(f"Auto Assemble tạo {self.table.rowCount()} đoạn — hãy rà soát timeline trước khi render.")
 def add_selected(self):
  r=self.list.currentRow()
  if 0<=r<len(self.sources):
   c=self.sources[r]
   try:a,b=trim_source_range(c.dur,self.trim_edges.isChecked())
   except ValueError:QMessageBox.warning(self,"Cắt video","Video quá ngắn để cắt 2 giây ở cả đầu và cuối.");return
   self.add_segment(c,a,b)
 def renumber(self):
  for r in range(self.table.rowCount()):self.table.item(r,0).setText(str(r+1))
 def remove_row(self):
  r=self.table.currentRow()
  if r>=0:self.table.removeRow(r);self.renumber()
 def move(self,d):
  r=self.table.currentRow();t=r+d
  if r<0 or t<0 or t>=self.table.rowCount():return
  data=[]
  for col in range(6):
   it=self.table.item(r,col);data.append((it.text(),it.data(Qt.UserRole),bool(it.flags()&Qt.ItemIsEditable)))
  self.table.removeRow(r);self.table.insertRow(t)
  for col,(v,path,editable) in enumerate(data):
   it=QTableWidgetItem(v)
   if not editable:it.setFlags(it.flags()&~Qt.ItemIsEditable)
   if path is not None:it.setData(Qt.UserRole,path)
   self.table.setItem(t,col,it)
  self.table.selectRow(t);self.renumber()
 def apply_trim(self):
  r=self.table.currentRow()
  if r<0:return
  try:
   a=float(self.table.item(r,2).text());b=float(self.table.item(r,3).text());p=self.table.item(r,1).data(Qt.UserRole);c=next(c for c in self.sources if c.path==p)
   if a<0 or b<=a or b>c.dur+.01:raise ValueError("In/Out không hợp lệ.")
   self.table.item(r,4).setText(f"{b-a:.2f}");self.status.setText("Đã áp dụng Trim.")
  except Exception as e:QMessageBox.warning(self,"Trim",str(e))
 def choose_output(self):
  p,_=QFileDialog.getSaveFileName(self,"Lưu video",self.output.text(),"MP4 (*.mp4)")
  if p:
   ext=".mov" if self.container.currentText()=="MOV" else ".mp4"
   stem=p[:-4] if p.lower().endswith((".mp4",".mov")) else p
   self.output.setText(stem+ext)
 def choose_lut(self):
  p,_=QFileDialog.getOpenFileName(self,"Chọn LUT","","LUT 3D (*.cube)")
  if p:self.lutpath.setText(p)
 def render(self):
  if self.lutpath.text().strip() and not Path(self.lutpath.text().strip()).is_file():QMessageBox.warning(self,"LUT","Tệp LUT không tồn tại.");return
  if not exe("ffmpeg"):QMessageBox.warning(self,"FFmpeg","Cài FFmpeg và thêm ffmpeg.exe vào PATH.");return
  segments=[]
  for r in range(self.table.rowCount()):
   try:
    p=self.table.item(r,1).data(Qt.UserRole);a=float(self.table.item(r,2).text());b=float(self.table.item(r,3).text());c=next(c for c in self.sources if c.path==p)
    if 0<=a<b<=c.dur+.01:segments.append((p,a,b))
   except:pass
  if not segments:QMessageBox.warning(self,"Timeline","Không có clip hợp lệ.");return
  out=self.output.text().strip()
  if not out:QMessageBox.warning(self,"Output","Chọn nơi lưu.");return
  settings=ExportSettings(self.resolution.currentText(),self.container.currentText(),self.codec.currentText(),int(self.fps.currentText()),int(self.bitrate.currentText().split()[0]),self.ratio.currentText())
  try:settings.validate()
  except ValueError as e:QMessageBox.warning(self,"Export settings",str(e));return
  out=str(Path(out).with_suffix(settings.extension))
  self.output.setText(out);self.renderbtn.setEnabled(False);self.cancelbtn.setEnabled(True);self.worker=Renderer(segments,self.music,out,settings,self.genre.currentText(),self.musiccheck.isChecked(),self.fade.isChecked(),self.lutpath.text().strip() or None,self.auto_light.isChecked(),self.auto_color.isChecked(),self.auto_wb.isChecked())
  self.worker.progress.connect(lambda p,m:(self.progress.setValue(p),self.status.setText(m)));self.worker.done.connect(self.render_done);self.worker.fail.connect(self.render_fail);self.worker.start()
 def cancel_render(self):
  if self.worker and self.worker.isRunning():
   self.worker.cancel();self.cancelbtn.setEnabled(False);self.status.setText("Đã yêu cầu hủy; đang chờ FFmpeg kết thúc bước hiện tại…")
 def update_output_extension(self,container):
  current=Path(self.output.text());ext=".mov" if container=="MOV" else ".mp4"
  self.output.setText(str(current.with_suffix(ext)))
 def set_language(self,language):
  english=language=="English"
  self.setWindowTitle("KHIETTRAN Autobeat Cut")
  translations={vi:en for vi,en in {
   "01 NGUỒN VIDEO — PHÂN TÍCH CẢNH AI":"01 SOURCE MEDIA — AI SCENE ANALYSIS", "＋ Nhập video":"＋ Import video", "✦ AI phân tích":"✦ AI Analyze", "✦ Phân tích AI":"✦ AI Analyze", "Rất lớn":"Extra large", "Trung bình":"Medium", "Nhỏ":"Small", "Chế độ xem":"View", "Xem trước video nguồn":"Source Preview", "Chọn video nguồn để xem trước":"Select a source to preview", "▶ Phát/Tạm dừng":"▶ Play/Pause", "02 NHẠC VÀ KẾ HOẠCH DỰNG":"02 MUSIC & EDIT PLAN", "♫ Chọn nhạc":"♫ Choose music", "Chưa chọn nhạc":"No music selected", "Chọn nhạc":"Choose music", "Dùng nhạc nền":"Use background music", "Phân tích BPM (thử nghiệm)":"Analyze BPM (beta)", "04 DÒNG THỜI GIAN — CLIP / CẮT / SẮP XẾP":"04 TIMELINE — CLIP / TRIM / ORDER", "✦ Dựng tự động":"✦ Auto Assemble", "Áp dụng cắt":"Apply Trim", "Vào (giây)":"In (s)", "Ra (giây)":"Out (s)", "Thời lượng (giây)":"Duration (s)", "Ghi chú AI":"AI notes", "DÒNG THỜI GIAN ÂM THANH — chưa có nhạc":"AUDIO TIMELINE — no music selected", "▶ Nghe thử âm thanh":"▶ Preview audio", "05 KẾT XUẤT VIDEO":"05 RENDER & EXPORT", "Làm mờ nhạc đầu":"Fade music in", "▶ KẾT XUẤT VIDEO":"▶ RENDER VIDEO", "Hủy kết xuất":"Cancel render", "Độ phân giải":"Resolution", "Định dạng tệp":"Container", "Tốc độ khung hình":"FPS", "Ngôn ngữ":"Language", "Tệp đầu ra":"Output", "Bitrate video":"Video bitrate", "Thể loại":"Genre", "Nhịp dựng":"Pacing", "Tỷ lệ":"Aspect ratio", "Tỷ lệ khung hình":"Aspect ratio", "LUT màu":"Color LUT", "Tự động ánh sáng (AI hỗ trợ)":"Auto lighting (AI-assisted)", "Tự động màu sắc (AI hỗ trợ)":"Auto color correction (AI-assisted)", "Tự động cân bằng trắng (AI hỗ trợ)":"Auto white balance (AI-assisted)", "Tự động bỏ 2 giây đầu/cuối mỗi video nguồn":"Trim first/last 2 seconds of each source", "Chọn nơi lưu":"Choose output", "Chọn LUT .cube":"Choose LUT .cube", "Chọn source để xem trước":"Select a source to preview", "− Xóa":"− Remove", "＋ Thêm":"＋ Add", "↑":"↑", "↓":"↓", "Không dùng LUT / No LUT":"No LUT selected", "Không dùng LUT":"No LUT selected"
  }.items()}
  reverse={en:vi for vi,en in translations.items()}
  mapping=translations if english else reverse
  for widget_type in (QLabel,QPushButton,QGroupBox,QCheckBox):
   for widget in self.findChildren(widget_type):
    current=widget.text()
    if current in mapping:widget.setText(mapping[current])
  headers=["#","Clip","In (s)","Out (s)","Độ dài (s)","AI notes"] if english else ["#","Clip","Vào (giây)","Ra (giây)","Thời lượng (giây)","Ghi chú AI"]
  self.table.setHorizontalHeaderLabels(headers)
  view_items=[("Extra large","Rất lớn"),("Medium","Trung bình"),("Small","Nhỏ")]
  for i,(en,vi) in enumerate(view_items):self.view.setItemText(i,en if english else vi)
  self.lutpath.setPlaceholderText("No LUT selected" if english else "Không dùng LUT")
  self.status.setText("Ready — local computer-vision analysis; no footage is uploaded." if english else "Sẵn sàng — phân tích hình ảnh cục bộ; video không được tải lên mạng.")
 def render_done(self,p):self.renderbtn.setEnabled(True);self.cancelbtn.setEnabled(False);QMessageBox.information(self,"Hoàn tất",f"Đã xuất và kiểm tra metadata:\n{p}")
 def render_fail(self,m):self.renderbtn.setEnabled(True);self.cancelbtn.setEnabled(False);self.status.setText("Render thất bại hoặc đã hủy.");QMessageBox.critical(self,"Render thất bại / Render failed",m)
def main():
 app=QApplication(sys.argv);w=Window();w.show();sys.exit(app.exec())
if __name__=="__main__":main()
