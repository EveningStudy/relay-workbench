"""Operator aids require occupied evidence or an actual suppression vote."""
from pathlib import Path
import inspect
from unittest.mock import patch
import numpy as np
from p2.fusion.prior_clusters import PriorClusters
from p2.ui.change_markers import ChangeMarkers,box_segments


def test_connected_cell_counts_match_original_with_duplicates_and_speckles():
    from scipy import ndimage
    from p2.ui.change_markers import connected
    rng=np.random.default_rng(63)
    points=rng.integers(0,35,(2400,3))*.02
    points=np.concatenate([points,points[:200],np.array([[x,0,0] for x in range(8)])*.02])
    coords=np.floor(points/.02+1e-5).astype(int);low=coords.min(0)
    grid=np.zeros(coords.max(0)-low+1,bool);grid[tuple((coords-low).T)]=True
    labels,n=ndimage.label(grid,np.ones((3,3,3)));per_point=labels[tuple((coords-low).T)]
    expected=[np.flatnonzero(per_point==label) for label in range(1,n+1)
              if len(np.unique(coords[per_point==label],axis=0))>=5]
    actual=connected(points,.02)
    assert len(actual)==len(expected)
    assert all(np.array_equal(a,b) for a,b in zip(actual,expected))


def test_support_hull_uses_same_region_without_interior_triangulation():
    from scipy.spatial import Delaunay,ConvexHull
    rng=np.random.default_rng(5);support=rng.random((2000,2));queries=rng.uniform(-.1,1.1,(4000,2))
    expected=Delaunay(support).find_simplex(queries)>=0
    actual=Delaunay(support[ConvexHull(support).vertices]).find_simplex(queries)>=0
    assert np.array_equal(actual,expected)


def test_evidence_markers_without_file_or_truth_access():
    table=np.array([[x,y,.9] for x in np.arange(0,.5,.02) for y in np.arange(0,.5,.02)])
    old=np.array([[.1+x,.1+y,.96+z] for x in np.arange(0,.08,.02) for y in np.arange(0,.08,.02) for z in [0,.02,.04,.06]])
    prior=np.concatenate([table,old]);clusters=PriorClusters(prior)
    cfg={'novel_distance_m':.04,'novel_min_voxels':5,'novel_confirmations':2}
    detector=ChangeMarkers(prior,clusters,.02,cfg);new=old+[.25,0,0]
    points=np.concatenate([table,old,new]);live=np.ones(len(points),bool);sources=np.ones(len(points),np.uint8)
    states=np.zeros(len(prior),np.int8)
    # This helper accepts arrays and prior components; even file access is forbidden.
    with patch('builtins.open',side_effect=AssertionError('unexpected file access')),patch.object(Path,'read_text',side_effect=AssertionError('unexpected file access')):
        assert detector.update(points,live,sources,states,[])==[]
        rows=detector.update(points,live,sources,states,[])
        assert [r['kind'] for r in rows]==['new']
        assert np.allclose(np.mean(rows[0]['bounds'],axis=0),np.mean([new.min(0),new.max(0)],axis=0))
        # Disappearance/occlusion is insufficient for a removal annotation.
        assert not any(r['kind']=='removed' for r in detector.update(new,np.ones(len(new),bool),sources[:len(new)],states,[{'id':1,'clear':False}]))
        states[clusters.components[0]['ids']]=2
        rows=detector.update(new,np.ones(len(new),bool),sources[:len(new)],states,[{'id':1,'clear':True}])
        assert {r['kind'] for r in rows}=={'new','removed'}
        # Stale novel geometry cannot cause NEW.
        rows=detector.update(new,np.zeros(len(new),bool),sources[:len(new)],states,[])
        assert not rows
    assert len(box_segments([[0,0,0],[1,1,1]]))==12
    assert len(box_segments([[0,0,0],[1,1,1]],True))>12
    assert list(inspect.signature(ChangeMarkers.update).parameters)==['self','points','live','sources','prior_states','cluster_trace','observed_points']


def test_new_bounds_include_observed_cell_extent_plus_margin():
    table=np.array([[x,y,.9] for x in np.arange(0,.5,.02) for y in np.arange(0,.5,.02)])
    clusters=PriorClusters(table)
    cfg={'novel_distance_m':.04,'novel_min_voxels':5,'novel_confirmations':1,'marker_margin_m':.008}
    detector=ChangeMarkers(table,clusters,.02,cfg)
    centres=np.array([[.21+x,.21+y,.97+z] for x in [0,.02] for y in [0,.02] for z in [0,.02,.04]])
    observed=np.concatenate([centres-[.009,.009,.009],centres+[.009,.009,.009]])
    rows=detector.update(centres,np.ones(len(centres),bool),np.ones(len(centres),np.int64),np.zeros(len(table),np.int8),[],observed)
    assert len(rows)==1
    lo,hi=np.array(rows[0]['bounds'])
    assert np.all(lo<=observed.min(0)-.008) and np.all(hi>=observed.max(0)+.008)
    assert np.all(lo<=centres.min(0)-.01) and np.all(hi>=centres.max(0)+.01)
