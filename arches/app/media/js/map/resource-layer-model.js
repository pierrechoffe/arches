define([
    'openlayers',
    'underscore',
    'arches',
    'map/layer-model'
], function(ol, _, arches, LayerModel) {
    var hexToRgb = function (hex) {
        var result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : null;
    };

    return function(config, featureCallback) {
        config = _.extend({
            entitytypeid: 'all',
            vectorColor: '#808080'
        }, config);

        var rgb = hexToRgb(config.vectorColor);

        var style = new ol.style.Style({
            text: new ol.style.Text({
                text: '\uf041',
                font: 'normal 33px FontAwesome',
                textBaseline: 'Bottom',
                fill: new ol.style.Fill({
                    color: 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',1)',
                })
            })
        });

        var source = new ol.source.GeoJSON({
            projection: 'EPSG:3857',
            url: arches.urls.map_markers + config.entitytypeid
        });

        if (typeof featureCallback === 'function') {
            var loadListener = source.on('change', function(e) {
                if (source.getState() == 'ready') {
                    featureCallback(source.getFeatures());
                    ol.Observable.unByKey(loadListener);
                }
            });
        }

        var vectorLayer = new ol.layer.Vector({
            maxResolution: arches.mapDefaults.cluster_min,
            source: source,
            style: style
        });

        var clusterSource = new ol.source.Cluster({
            distance: 40,
            source: source
        });

        var styleCache = {};

        var clusterStyle = function(feature, resolution) {
            var size = feature.get('features').length;
            var radius = 10;
            if (size > 200) {
                radius = 18;
            } else if (size > 150) {
                radius = 16;
            } else if (size > 100) {
                radius = 14;
            } else if (size > 50) {
                radius = 12;
            }
            var style = [new ol.style.Style({
                image: new ol.style.Circle({
                    radius: radius,
                    stroke: new ol.style.Stroke({
                        color: 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.4)',
                        width: radius
                    }),
                    fill: new ol.style.Fill({
                        color: 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.8)',
                    })
                }),
                text: new ol.style.Text({
                    text: size.toString(),
                    fill: new ol.style.Fill({
                        color: '#fff'
                    })
                })
            })];
            return style;
        };

        var clusterLayer = new ol.layer.Vector({
            minResolution: arches.mapDefaults.cluster_min,
            source: clusterSource,
            style: clusterStyle
        });

        var layerGroup = new ol.layer.Group({
            layers: [
                vectorLayer,
                clusterLayer
            ]
        });

        return new LayerModel(_.extend({
                layer: layerGroup,
                onMap: true
            }, config)
        );
    };
});