"""Screen-right must agree with forward crossed with screen-up."""
import pytest
from navigation import camdir_orientation,relative_deflection

@pytest.mark.parametrize('camera',[(0,0,0),(70,0,-97),(-117,-25,156)])
def test_right_axis_has_physical_screen_handedness(camera):
    f,r,u=camdir_orientation(camera)
    cross=(f[1]*u[2]-f[2]*u[1],f[2]*u[0]-f[0]*u[2],f[0]*u[1]-f[1]*u[0])
    assert r==pytest.approx(cross)

def test_facing_positive_x_with_positive_z_up_places_negative_y_on_right():
    angles=relative_deflection((0,0,0),(0,0,0),(10,-10,0))
    assert angles['yaw_offset_deg']==pytest.approx(45)
    assert angles['pitch_offset_deg']==pytest.approx(0)
