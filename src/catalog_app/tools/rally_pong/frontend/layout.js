// Pure camera-fit math, independently tested at phone, desktop and landscape sizes.
// Bounds include the raised chassis, not just the playable rectangle.
export function courtLayout(width, height, intro = false) {
  width = Math.max(1, Number(width) || 1); height = Math.max(1, Number(height) || 1);
  const portrait = width <= 720 && height > 450;
  const short = height < 370;
  let left, right, top, bottom;
  if (intro && portrait) {
    left = 12; right = width - 12;
    top = height < 550 ? 252 : 286; bottom = height - 32;
  } else if (intro) {
    left = width * .405; right = width - Math.min(25, width * .03);
    top = short ? 40 : 67; bottom = height - (short ? 30 : 74);
  } else {
    left = Math.min(24, width * .04); right = width - left;
    top = short ? 64 : portrait ? 125 : 113;
    bottom = height - (short ? 58 : portrait ? 107 : 90);
  }
  if (bottom < top + 40) { top = height * .2; bottom = height * .8; }
  if (right < left + 20) { left = width * .1; right = width * .9; }
  const worldWidth = intro && !portrait ? 24.2 : 22.8;
  const worldHeight = intro && !portrait ? 15.3 : 12.9;
  const scale = Math.max(.01, Math.min((right - left) / worldWidth, (bottom - top) / worldHeight));
  const viewHeight = height / scale;
  const centerX = (left + right) / 2, centerY = (top + bottom) / 2;
  const pitch = 26 / Math.hypot(26, 19);
  return {
    scale, viewHeight, targetX: (width / 2 - centerX) / scale,
    targetZ: (height / 2 - centerY) / (scale * pitch),
    yaw: intro && !portrait ? -.16 : 0, portrait,
    bounds: { left, right, top, bottom }, worldWidth, worldHeight,
  };
}
