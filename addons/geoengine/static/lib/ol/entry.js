import Collection from "ol/Collection.js";
import Feature from "ol/Feature.js";
import Geolocation from "ol/Geolocation.js";
import Map from "ol/Map.js";
import Overlay from "ol/Overlay.js";
import View from "ol/View.js";

import Attribution from "ol/control/Attribution.js";
import Control from "ol/control/Control.js";
import FullScreen from "ol/control/FullScreen.js";
import MousePosition from "ol/control/MousePosition.js";
import OverviewMap from "ol/control/OverviewMap.js";
import Rotate from "ol/control/Rotate.js";
import ScaleLine from "ol/control/ScaleLine.js";
import ZoomSlider from "ol/control/ZoomSlider.js";
import Zoom from "ol/control/Zoom.js";

import {
    click,
    platformModifierKeyOnly,
    pointerMove,
} from "ol/events/condition.js";

import {extend, getCenter, getTopLeft, isEmpty} from "ol/extent.js";

import GeoJSON from "ol/format/GeoJSON.js";
import MVT from "ol/format/MVT.js";

import Geometry from "ol/geom/Geometry.js";
import LineString from "ol/geom/LineString.js";
import MultiLineString from "ol/geom/MultiLineString.js";
import Point from "ol/geom/Point.js";
import Polygon from "ol/geom/Polygon.js";

import DragBox from "ol/interaction/DragBox.js";
import Draw from "ol/interaction/Draw.js";
import Modify from "ol/interaction/Modify.js";
import Select from "ol/interaction/Select.js";
import Snap from "ol/interaction/Snap.js";

import Group from "ol/layer/Group.js";
import ImageLayer from "ol/layer/Image.js";
import Heatmap from "ol/layer/Heatmap.js";
import Layer from "ol/layer/Layer.js";
import TileLayer from "ol/layer/Tile.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorTileLayer from "ol/layer/VectorTile.js";
import WebGLVectorLayer from "ol/layer/WebGLVector.js";

import {fromLonLat, get as getProjection, toLonLat} from "ol/proj.js";
import {register} from "ol/proj/proj4.js";

import Cluster from "ol/source/Cluster.js";
import ImageWMS from "ol/source/ImageWMS.js";
import OSM from "ol/source/OSM.js";
import TileWMS from "ol/source/TileWMS.js";
import VectorSource from "ol/source/Vector.js";
import VectorTileSource from "ol/source/VectorTile.js";
import WMTS from "ol/source/WMTS.js";
import XYZ from "ol/source/XYZ.js";

import CircleStyle from "ol/style/Circle.js";
import Fill from "ol/style/Fill.js";
import Stroke from "ol/style/Stroke.js";
import Style from "ol/style/Style.js";
import Text from "ol/style/Text.js";

import {getArea, getLength} from "ol/sphere.js";

import WMTSTileGrid from "ol/tilegrid/WMTS.js";

export {Collection, Feature, Geolocation, Map, Overlay, View};

export const control = {
    Attribution,
    Control,
    FullScreen,
    MousePosition,
    OverviewMap,
    Rotate,
    ScaleLine,
    Zoom,
    ZoomSlider,
};
export const events = {condition: {click, platformModifierKeyOnly, pointerMove}};
export const extent = {extend, getCenter, getTopLeft, isEmpty};
export const format = {GeoJSON, MVT};
export const geom = {Geometry, LineString, MultiLineString, Point, Polygon};
export const interaction = {DragBox, Draw, Modify, Select, Snap};
export const layer = {
    Group,
    Heatmap,
    Layer,
    Image: ImageLayer,
    Tile: TileLayer,
    Vector: VectorLayer,
    VectorTile: VectorTileLayer,
    WebGLVector: WebGLVectorLayer,
};
export const proj = {fromLonLat, get: getProjection, register, toLonLat};
export const source = {
    Cluster,
    ImageWMS,
    OSM,
    TileWMS,
    Vector: VectorSource,
    VectorTile: VectorTileSource,
    WMTS,
    XYZ,
};
export const style = {Circle: CircleStyle, Fill, Stroke, Style, Text};
export const sphere = {getArea, getLength};
export const tilegrid = {WMTS: WMTSTileGrid};
