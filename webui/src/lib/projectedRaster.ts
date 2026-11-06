import ImageSource from 'ol/source/Image';
import type RasterSource from 'ol/source/Raster';
import type ImageWrapper from 'ol/Image';
import ImageState from 'ol/ImageState';
import type { Extent } from 'ol/extent';
import type Projection from 'ol/proj/Projection';
import type { ProjectionLike } from 'ol/proj';
import { unByKey } from 'ol/Observable';

/** Style native numeric tiles first, then reproject RGBA with Canvas 2D.
 * Passing the map projection directly to RasterSource would instead invoke
 * OpenLayers' WebGL float-data reprojection, even in compatibility mode.
 */
export class ProjectedRaster extends ImageSource {
  private frame: ImageWrapper | null = null;
  private changeKey;

  constructor(private raster: RasterSource, projection: ProjectionLike, private canRender = () => true) {
    super({ projection, interpolate: false });
    this.changeKey = raster.on('change', () => {
      this.frame = null;
      this.changed();
    });
  }

  get frameReady() { return this.canRender() && this.frame?.getState() === ImageState.LOADED; }

  override getImage(extent: Extent, resolution: number, pixelRatio: number, projection: Projection) {
    // RasterSource treats ERROR tiles as empty pixels. Returning null here
    // retains the last good image in the layer instead of publishing holes.
    if (!this.canRender()) { this.frame = null; return null; }
    this.frame = super.getImage(extent, resolution, pixelRatio, projection);
    return this.frame;
  }

  protected override getImageInternal(extent: Extent, resolution: number, pixelRatio: number, projection: Projection) {
    // ImageSource transforms this request into our declared native projection.
    return this.raster.getImage(extent, resolution, pixelRatio, projection);
  }

  protected override disposeInternal() {
    unByKey(this.changeKey);
    this.frame?.dispose();
    this.raster.dispose();
    super.disposeInternal();
  }
}
