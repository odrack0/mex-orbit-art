import numpy as np, math
from mesh_metrics import analyse

def cylinder(seg=12, h=2.0, r=1.0):
    V=[];F=[]
    for i in range(seg):
        a=2*math.pi*i/seg
        V.append([r*math.cos(a),-h/2,r*math.sin(a)]); V.append([r*math.cos(a),h/2,r*math.sin(a)])
    for i in range(seg):
        a0,a1=2*i,2*((i+1)%seg)
        F+= [[a0,a1,a0+1],[a1,a1+1,a0+1]]
    return np.array(V), np.array(F)

def uvsphere(seg=12, rings=8, r=1.0):
    V=[];F=[]
    for j in range(rings+1):
        phi=math.pi*j/rings
        for i in range(seg):
            th=2*math.pi*i/seg
            V.append([r*math.sin(phi)*math.cos(th), r*math.cos(phi), r*math.sin(phi)*math.sin(th)])
    for j in range(rings):
        for i in range(seg):
            a=j*seg+i; b=j*seg+(i+1)%seg; c=a+seg; d=b+seg
            F+=[[a,b,c],[b,d,c]]
    return np.array(V), np.array(F)

def cube():
    V=np.array([[x,y,z] for x in(-1,1) for y in(-1,1) for z in(-1,1)],float)
    F=np.array([[0,1,3],[0,3,2],[4,7,5],[4,6,7],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]])
    return V,F

for label,(V,F) in [("cyl12",cylinder(12)),("cyl8",cylinder(8)),("sphere16x10",uvsphere(16,10)),("cube",cube())]:
    r=analyse(V,F,None,None,name=label,heavy=True,res=256)
    print(f"{label:14} tris={r['tris']:5d} vw={r['verts_welded']:4d} rot={r['rot_sym_order']}({r['rot_sym_axis']},{r['rot_sym_frac']}) "
          f"quadratio={r['quad_tri_ratio']} open={r['open_shell']} bnd={r['boundary_edges']} "
          f"hidden={r['hidden_gamecam_ratio']} interior={r['interior_tri_ratio']} sil={r['silhouette_band_tri_share']} mirror={r['best_mirror']}={r['best_mirror_frac']}")
