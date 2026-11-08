from pathlib import Path
import datetime,shutil,ast
root=Path(__file__).resolve().parent
p=root/'agent.py'
s=p.read_text(encoding='utf-8')
backup=p.with_name('agent.py.backup-upload-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
shutil.copy2(p,backup)
s=s.replace('limit=500*1024*1024 if kind==\'video\' else 100*1024*1024','limit=4*1024*1024*1024')
s=s.replace('f.size>500*1024*1024','f.size>4*1024*1024*1024').replace('f.size>100*1024*1024','f.size>4*1024*1024*1024')
s=s.replace('500 MB','4 GiB').replace('100 MB','4 GiB')
s=s.replace('xhr.timeout=600000','xhr.timeout=7200000')
needle="    remaining=n\n    try:"
replacement="""    if shutil.disk_usage(upload_dir).free < n + 512*1024*1024:
     self.close_connection=True
     return self.output(507,{'error':'אין מספיק מקום פנוי בדיסק להעלאה זו'})
    self.connection.settimeout(120)
    remaining=n
    try:"""
assert s.count(needle)==1
s=s.replace(needle,replacement)
ast.parse(s)
p.write_text(s,encoding='utf-8')
print('Updated upload limits: 4 GiB; memory buffer: 1 MiB; browser timeout: 2 hours; disk-space preflight enabled.')
print('Backup:',backup)