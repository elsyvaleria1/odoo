/**
* geostats() is a tiny and standalone javascript library for classification 
* Project page - https://github.com/simogeo/geostats
* Copyright (c) 2011 Simon Georget, http://www.intermezzo-coop.eu
* Licensed under the MIT license
*/


var geostats = (function () {

var isInt = function(n) {
   return typeof n === 'number' && parseFloat(n) == parseInt(n, 10) && !isNaN(n);
}

var _t = function(str) {
	return str;
};

var isNumber = function(n) {
	  return !isNaN(parseFloat(n)) && isFinite(n);
}



if (!Array.prototype.indexOf) {
    Array.prototype.indexOf = function (searchElement, fromIndex) {
      if ( this === undefined || this === null ) {
        throw new TypeError( '"this" is null or not defined' );
      }

      var length = this.length >>> 0;

      fromIndex = +fromIndex || 0;

      if (Math.abs(fromIndex) === Infinity) {
        fromIndex = 0;
      }

      if (fromIndex < 0) {
        fromIndex += length;
        if (fromIndex < 0) {
          fromIndex = 0;
        }
      }

      for (;fromIndex < length; fromIndex++) {
        if (this[fromIndex] === searchElement) {
          return fromIndex;
        }
      }

      return -1;
    };
  }

var geostats = function(a) {

	this.objectID = '';
	this.separator = ' - ';
	this.legendSeparator = this.separator;
	this.method  = '';
	this.precision = 0;
	this.precisionflag = 'auto';
	this.roundlength	= 2;
	this.is_uniqueValues = false;
	this.debug =  false;
	this.silent = false;

	this.bounds  = Array();
	this.ranges  = Array();
	this.inner_ranges  = null;
	this.colors  = Array();
	this.counter = Array();

	this.stat_sorted	= null;
	this.stat_mean		= null;
	this.stat_median	= null;
	this.stat_sum		= null;
	this.stat_max		= null;
	this.stat_min		= null;
	this.stat_pop		= null;
	this.stat_variance	= null;
	this.stat_stddev	= null;
	this.stat_cov		= null;


	this.log = function(msg, force) {

		if(this.debug == true || force != null)
			console.log(this.objectID + "(object id) :: " + msg);

	};

	this.setBounds = function(a) {

		this.log('Setting bounds (' + a.length + ') : ' + a.join());

		this.bounds = Array()

		this.bounds = a;

	};

	this.setSerie = function(a) {

		this.log('Setting serie (' + a.length + ') : ' + a.join());

		this.serie = Array()
		this.serie = a;

	    this.resetStatistics();

		this.setPrecision();

	};

	this.setColors = function(colors) {

		this.log('Setting color ramp (' + colors.length + ') : '  + colors.join());

		this.colors = colors;

	};

	this.doCount = function() {

		if (this._nodata())
			return;


		var tmp = this.sorted();

		this.counter = new Array();

		if(this.is_uniqueValues == true) {
			for (var i = 0; i < this.bounds.length; i++) {
				this.counter[i]= 0;
			}
		} else {
			for (var i = 0; i < this.bounds.length -1; i++) {
				this.counter[i]= 0;
			}
		}

		for (var j=0; j < tmp.length; j++) {

			var cclass = this.getClass(tmp[j]);
			this.counter[cclass]++;

		}

	};

	this.setPrecision = function(decimals) {

		if(typeof decimals !== "undefined") {
			this.precisionflag = 'manual';
			this.precision = decimals;
		}

		if(this.precisionflag == 'auto') {

			for (var i = 0; i < this.serie.length; i++) {

				if (!isNaN((this.serie[i]+"")) && (this.serie[i]+"").toString().indexOf('.') != -1) {
					var precision = (this.serie[i] + "").split(".")[1].length;
				} else {
					var precision = 0;
				}

				if(precision > this.precision) {
					this.precision = precision;
				}

			}

		}
		if(this.precision > 20) {
			this.log('this.precision value (' + this.precision + ') is greater than max value. Automatic set-up to 20 to prevent "Uncaught RangeError: toFixed()" when calling decimalFormat() method.');
			this.precision = 20;
		}

		this.log('Calling setPrecision(). Mode : ' + this.precisionflag + ' - Decimals : '+ this.precision);

		this.serie = this.decimalFormat(this.serie);

	};

	this.decimalFormat = function(a) {

		var b = new Array();

		for (var i = 0; i < a.length; i++) {
			if (isNumber(a[i])) {
				b[i] = parseFloat(parseFloat(a[i]).toFixed(this.precision));
			} else {
				b[i] = a[i];
			}
		}

		return b;
	}

	this.setRanges = function() {

		this.ranges = Array();

		for (var i = 0; i < (this.bounds.length - 1); i++) {
			this.ranges[i] = this.bounds[i] + this.separator + this.bounds[i + 1];
		}
	};

	this.min = function(exclude = []) {

		if (this._nodata())
			return;

		if(!exclude.includes(this.serie[0])) this.stat_min = this.serie[0];
		else this.stat_min = 999999999999;


		for (var i = 0; i < this.pop(); i++) {
			if (this.serie[i] < this.stat_min && !exclude.includes(this.serie[i])) {
				this.stat_min = this.serie[i];
			}
		}

		return this.stat_min;
	};

	this.max = function(exclude = []) {

		if (this._nodata())
			return;

		if(!exclude.includes(this.serie[0])) this.stat_max = this.serie[0];
		else this.stat_max = -999999999999;

		for (var i = 0; i < this.pop(); i++) {
			if (this.serie[i] > this.stat_max && !exclude.includes(this.serie[i])) {
				this.stat_max = this.serie[i];
			}
		}

		return this.stat_max;
	};

	this.sum = function() {

		if (this._nodata())
			return;

		if (this.stat_sum  == null) {

			this.stat_sum = 0;
			for (var i = 0; i < this.pop(); i++) {
				this.stat_sum += parseFloat(this.serie[i]);
			}

		}

		return this.stat_sum;
	};

	this.pop = function() {

		if (this._nodata())
			return;

		if (this.stat_pop  == null) {

			this.stat_pop = this.serie.length;

		}

		return this.stat_pop;
	};

	this.mean = function() {

		if (this._nodata())
			return;

		if (this.stat_mean  == null) {

			this.stat_mean = parseFloat(this.sum() / this.pop());

		}

		return this.stat_mean;
	};

	this.median = function() {

		if (this._nodata())
			return;

		if (this.stat_median  == null) {

			this.stat_median = 0;
			var tmp = this.sorted();

			if (tmp.length % 2) {
				this.stat_median = parseFloat(tmp[(Math.ceil(tmp.length / 2) - 1)]);

			} else {
				this.stat_median = ( parseFloat(tmp[((tmp.length / 2) - 1)]) + parseFloat(tmp[(tmp.length / 2)]) ) / 2;
			}

		}

		return this.stat_median;
	};

	this.variance = function() {

		var round = (typeof round === "undefined") ? true : false;

		if (this._nodata())
			return;

		if (this.stat_variance  == null) {

			var tmp = 0, serie_mean = this.mean();
			for (var i = 0; i < this.pop(); i++) {
				tmp += Math.pow( (this.serie[i] - serie_mean), 2 );
			}

			this.stat_variance =  tmp / this.pop();

			if(round == true) {
				this.stat_variance = Math.round(this.stat_variance * Math.pow(10,this.roundlength) )/ Math.pow(10,this.roundlength);
			}

		}

		return this.stat_variance;
	};

	this.stddev = function(round) {

		var round = (typeof round === "undefined") ? true : false;

		if (this._nodata())
			return;

		if (this.stat_stddev  == null) {

			this.stat_stddev = Math.sqrt(this.variance());

			if(round == true) {
				this.stat_stddev = Math.round(this.stat_stddev * Math.pow(10,this.roundlength) )/ Math.pow(10,this.roundlength);
			}

		}

		return this.stat_stddev;
	};

	this.cov = function(round) {

		var round = (typeof round === "undefined") ? true : false;

		if (this._nodata())
			return;

		if (this.stat_cov  == null) {

			this.stat_cov = this.stddev() / this.mean();

			if(round == true) {
				this.stat_cov = Math.round(this.stat_cov * Math.pow(10,this.roundlength) )/ Math.pow(10,this.roundlength);
			}

		}

		return this.stat_cov;
	};

	this.resetStatistics = function() {
	    this.stat_sorted    = null;
	    this.stat_mean  = null;
	    this.stat_median    = null;
	    this.stat_sum       = null;
	    this.stat_max       = null;
	    this.stat_min       = null;
	    this.stat_pop       = null;
	    this.stat_variance  = null;
	    this.stat_stddev    = null;
	    this.stat_cov       = null;
	}

	this._nodata = function() {
		if (this.serie.length == 0) {

			if(this.silent) this.log("[silent mode] Error. You should first enter a serie!", true);
			else throw new TypeError("Error. You should first enter a serie!");
			return 1;
		} else
			return 0;

	};

	this._classificationCheck = function(nbClass) {

		if(nbClass >= this.pop()) {
			var errnum ='Error. ' + nbClass + ' classes are defined for only ' + this.pop() + ' values in serie ! For the current serie, no more than ' + (this.pop() - 1 ) + ' classes can be defined.';

			if(this.silent) this.log(errnum, true);
			else {
				alert(errnum);
				throw new TypeError(errnum);
			}

		}

	};

	this._nbClassInt = function(nbClass) {

		var nbclassTmp = parseInt(nbClass, 10);
		if (isNaN(nbclassTmp)) {
			if(this.silent) this.log("[silent mode] '" + nbclassTmp + "' is not a valid integer. Enable to set class number.", true);
			else throw new TypeError("'" + nbclassTmp + "' is not a valid integer. Enable to set class number.");
		} else {
			return nbclassTmp;
		}

	};

	this._hasNegativeValue = function() {

		for (var i = 0; i < this.serie.length; i++) {
		if(this.serie[i] < 0)
			return true;
	    }

		return false;
	};

	this._hasZeroValue = function() {

		for (var i = 0; i < this.serie.length; i++) {
		if(parseFloat(this.serie[i]) === 0)
			return true;
	    }

		return false;
	};

	this.sorted = function() {

		if (this.stat_sorted  == null) {

			if(this.is_uniqueValues == false) {
				this.stat_sorted = this.serie.sort(function(a, b) {
					return a - b;
				});
			} else {
				this.stat_sorted = this.serie.sort(function(a,b){
					var nameA=a.toString().toLowerCase(), nameB=b.toString().toLowerCase();
				    if(nameA < nameB) return -1;
				    if(nameA > nameB) return 1;
				    return 0;
				})
			}
		}

		return this.stat_sorted;

	};

	this.info = function() {

		if (this._nodata())
			return;

		var content = '';
		content += _t('Population') + ' : ' + this.pop() + ' - [' + _t('Min')
				+ ' : ' + this.min() + ' | ' + _t('Max') + ' : ' + this.max()
				+ ']' + "\n";
		content += _t('Mean') + ' : ' + this.mean() + ' - ' + _t('Median')	+ ' : ' + this.median() + "\n";
		content += _t('Variance') + ' : ' + this.variance() + ' - ' + _t('Standard deviation')	+ ' : ' + this.stddev()
				+ ' - ' + _t('Coefficient of variation')	+ ' : ' + this.cov() + "\n";

		return content;
	};

	this.setClassManually = function(array) {

		if (this._nodata())
	        return;

	    if(array[0] !== this.min() || array[array.length-1] !== this.max()) {
		if(this.silent) this.log("[silent mode] " + _t('Given bounds may not be correct! please check your input.\nMin value : ' + this.min() + ' / Max value : ' + this.max()), true);
			else throw new TypeError(_t('Given bounds may not be correct! please check your input.\nMin value : ' + this.min() + ' / Max value : ' + this.max()));
		return;
	    }

	    this.setBounds(array);
	    this.setRanges();

	    this.method = _t('manual classification') + ' (' + (array.length -1) + ' ' + _t('classes') + ')';

	    return this.bounds;
	};

	this.getClassEqInterval = function(nbClass, forceMin, forceMax) {

		var nbClass = this._nbClassInt(nbClass);

		if (this._nodata())
	        return;

		var tmpMin = (typeof forceMin === "undefined") ? this.min() : forceMin;
		var tmpMax = (typeof forceMax === "undefined") ? this.max() : forceMax;

	    var a = Array();
	    var val = tmpMin;
	    var interval = (tmpMax - tmpMin) / nbClass;

	    for (var i = 0; i <= nbClass; i++) {
	        a[i] = val;
	        val += interval;
	    }

	    a[nbClass] = tmpMax;

	    this.setBounds(a);
	    this.setRanges();

	    this.method = _t('eq. intervals') + ' (' + nbClass + ' ' + _t('classes') + ')';

	    return this.bounds;
	};


	this.getQuantiles = function(nbClass) {

		var nbClass = this._nbClassInt(nbClass);

		var tmp = this.sorted();
		var quantiles = [];

		var step = this.pop() / nbClass;
		for (var i = 1; i < nbClass; i++) {
			var qidx = Math.round(i*step+0.49);
			quantiles.push(tmp[qidx-1]);
		}

		return quantiles;
	};

	this.getClassQuantile = function(nbClass) {

		var nbClass = this._nbClassInt(nbClass);

		if (this._nodata())
			return;

		this._classificationCheck(nbClass);

		var tmp = this.sorted();
		var bounds = this.getQuantiles(nbClass);
		bounds.unshift(tmp[0]);

		if (bounds[tmp.length - 1] !== tmp[tmp.length - 1])
			bounds.push(tmp[tmp.length - 1]);

		this.setBounds(bounds);
		this.setRanges();

		this.method = _t('quantile') + ' (' + nbClass + ' ' + _t('classes') + ')';

		return this.bounds;

	};

	this.getClassStdDeviation = function(nbClass, matchBounds) {

		var nbClass = this._nbClassInt(nbClass);

		if (this._nodata())
	        return;

	    var tmpMax = this.max();
		var tmpMin = this.min();
		var tmpStdDev = this.stddev();
		var tmpMean = this.mean();

	    var a = Array();

	    if(nbClass % 2 == 1) {

		var infBound = Math.floor(nbClass / 2);

		var supBound = infBound + 1;

		a[infBound] = tmpMean - (tmpStdDev / 2);
		a[supBound] = tmpMean + (tmpStdDev / 2);

		for (var i = infBound - 1; i > 0; i--) {
			var val = a[i+1] - tmpStdDev;
		        a[i] = val;
		    }

		for (var i = supBound + 1; i < nbClass; i++) {
			var val = a[i-1] + tmpStdDev;
		        a[i] = val;
		    }

	    } else {

		var meanBound = nbClass / 2;

		a[meanBound] = tmpMean;

		for (var i = meanBound - 1; i > 0; i--) {
			var val = a[i+1] - tmpStdDev;
		        a[i] = val;
		    }

		for (var i = meanBound + 1; i < nbClass; i++) {
			var val = a[i-1] + tmpStdDev;
		        a[i] = val;
		    }
	    }


	    a[0] = (typeof matchBounds === "undefined") ? a[1]- tmpStdDev : tmpMin;

	a[nbClass] = (typeof matchBounds === "undefined") ? a[nbClass-1] + tmpStdDev : tmpMax;

	    this.setBounds(a);
	    this.setRanges();

	    this.method = _t('std deviation') + ' (' + nbClass + ' ' + _t('classes')+ ')';

	    return this.bounds;
	};


	this.getClassGeometricProgression = function(nbClass) {

		var nbClass = this._nbClassInt(nbClass);

		if (this._nodata())
	        return;

	    if(this._hasNegativeValue() || this._hasZeroValue()) {
		if(this.silent) this.log("[silent mode] " + _t('geometric progression can\'t be applied with a serie containing negative or zero values.'), true);
			else throw new TypeError(_t('geometric progression can\'t be applied with a serie containing negative or zero values.'));
		return;
	    }

	    var a = Array();
	    var tmpMin = this.min();
	    var tmpMax = this.max();

	    var logMax = Math.log(tmpMax) / Math.LN10;
	    var logMin = Math.log(tmpMin) / Math.LN10;;

	    var interval = (logMax - logMin) / nbClass;

	    for (var i = 0; i < nbClass; i++) {
		if(i == 0) {
			a[i] = logMin;
		} else {
			a[i] = a[i-1] + interval;
		}
	    }

	    a = a.map(function(x) { return Math.pow(10, x); });

	    a.push(this.max());

	    this.setBounds(a);
	    this.setRanges();

	    this.method = _t('geometric progression') + ' (' + nbClass + ' ' + _t('classes') + ')';

	    return this.bounds;
	};

	this.getClassArithmeticProgression = function(nbClass) {

		var nbClass = this._nbClassInt(nbClass);

		if (this._nodata())
	        return;

	    var denominator = 0;

	    for (var i = 1; i <= nbClass; i++) {
	        denominator += i;
	    }

	    var a = Array();
	    var tmpMin = this.min();
	    var tmpMax = this.max();

	    var interval = (tmpMax - tmpMin) / denominator;

	    for (var i = 0; i <= nbClass; i++) {
		if(i == 0) {
			a[i] = tmpMin;
			} else if(i == nbClass) {
				a[i] = tmpMax;
			} else {
			a[i] = a[i-1] + (i * interval);
		}
	    }

	    this.setBounds(a);
	    this.setRanges();

	    this.method = _t('arithmetic progression') + ' (' + nbClass + ' ' + _t('classes') + ')';

	    return this.bounds;
	};

	this.getClassJenks2 = function(nbClass) {

		var nbClass = this._nbClassInt(nbClass);

		if (this._nodata())
			return;

		this._classificationCheck(nbClass);

		var dataList = this.sorted();

		var mat1 = []
		for ( var x = 0, xl = dataList.length + 1; x < xl; x++) {
			var temp = []
			for ( var j = 0, jl = nbClass + 1; j < jl; j++) {
				temp.push(0)
			}
			mat1.push(temp)
		}

		var mat2 = []
		for ( var i = 0, il = dataList.length + 1; i < il; i++) {
			var temp2 = []
			for ( var c = 0, cl = nbClass + 1; c < cl; c++) {
				temp2.push(0)
			}
			mat2.push(temp2)
		}

		for ( var y = 1, yl = nbClass + 1; y < yl; y++) {
			mat1[0][y] = 1
			mat2[0][y] = 0
			for ( var t = 1, tl = dataList.length + 1; t < tl; t++) {
				mat2[t][y] = Infinity
			}
			var v = 0.0
		}

		for ( var l = 2, ll = dataList.length + 1; l < ll; l++) {
			var s1 = 0.0
			var s2 = 0.0
			var w = 0.0
			for ( var m = 1, ml = l + 1; m < ml; m++) {
				var i3 = l - m + 1
				var val = parseFloat(dataList[i3 - 1])
				s2 += val * val
				s1 += val
				w += 1
				v = s2 - (s1 * s1) / w
				var i4 = i3 - 1
				if (i4 != 0) {
					for ( var p = 2, pl = nbClass + 1; p < pl; p++) {
						if (mat2[l][p] >= (v + mat2[i4][p - 1])) {
							mat1[l][p] = i3
							mat2[l][p] = v + mat2[i4][p - 1]
						}
					}
				}
			}
			mat1[l][1] = 1
			mat2[l][1] = v
		}

		var k = dataList.length
		var kclass = []

		for (var i = 0; i <= nbClass; i++) {
			kclass.push(0);
		}

		kclass[nbClass] = parseFloat(dataList[dataList.length - 1])
		kclass[0] = parseFloat(dataList[0])
		var countNum = nbClass
		while (countNum >= 2) {
			var id = parseInt((mat1[k][countNum]) - 2)
			kclass[countNum - 1] = dataList[id]
			k = parseInt((mat1[k][countNum] - 1))
			countNum -= 1
		}
		if (kclass[0] == kclass[1]) {
			kclass[0] = 0
		}

		this.setBounds(kclass);
		this.setRanges();


		this.method = _t('Jenks2') + ' (' + nbClass + ' ' + _t('classes') + ')';

		return this.bounds;
	}

	this.getClassJenks = function(nbClass) {

		var nbClass = this._nbClassInt(nbClass);

		if (this._nodata())
			return;

		this._classificationCheck(nbClass);

		var dataList = this.sorted();

		var jenksMatrices = function(data, n_classes) {

			var lower_class_limits = [],
				variance_combinations = [],
				i, j,
				variance = 0;

			for (var i = 0; i < data.length + 1; i++) {
				var tmp1 = [], tmp2 = [];
				for (var j = 0; j < n_classes + 1; j++) {
					tmp1.push(0);
					tmp2.push(0);
				}
				lower_class_limits.push(tmp1);
				variance_combinations.push(tmp2);
			}

			for (var i = 1; i < n_classes + 1; i++) {
				lower_class_limits[1][i] = 1;
				variance_combinations[1][i] = 0;
				for (var j = 2; j < data.length + 1; j++) {
					variance_combinations[j][i] = Infinity;
				}
			}

			for (var l = 2; l < data.length + 1; l++) {

				var sum = 0,
					sum_squares = 0,
					w = 0,
					i4 = 0;

				for (var m = 1; m < l + 1; m++) {

					var lower_class_limit = l - m + 1,
						val = data[lower_class_limit - 1];

					w++;

					sum += val;
					sum_squares += val * val;

					variance = sum_squares - (sum * sum) / w;

					i4 = lower_class_limit - 1;

					if (i4 !== 0) {
						for (var j = 2; j < n_classes + 1; j++) {
							if (variance_combinations[l][j] >=
								(variance + variance_combinations[i4][j - 1])) {
								lower_class_limits[l][j] = lower_class_limit;
								variance_combinations[l][j] = variance +
									variance_combinations[i4][j - 1];
							}
						}
					}
				}

				lower_class_limits[l][1] = 1;
				variance_combinations[l][1] = variance;
			}

			return {
				lower_class_limits: lower_class_limits,
				variance_combinations: variance_combinations
			};
		};

        var matrices = jenksMatrices(dataList, nbClass),
            lower_class_limits = matrices.lower_class_limits,
            k = dataList.length - 1,
            kclass = [],
            countNum = nbClass;

        kclass[nbClass] = dataList[dataList.length - 1];
        kclass[0] = dataList[0];

        while (countNum > 1) {
            kclass[countNum - 1] = dataList[lower_class_limits[k][countNum] - 2];
            k = lower_class_limits[k][countNum] - 1;
            countNum--;
        }

		this.setBounds(kclass);
		this.setRanges();


		this.method = _t('Jenks') + ' (' + nbClass + ' ' + _t('classes') + ')';

		return this.bounds;
	}


	this.getClassUniqueValues = function() {

		if (this._nodata())
			return;

		this.is_uniqueValues = true;

		var tmp = this.sorted();

		var a = Array();

		for (var i = 0; i < this.pop(); i++) {
			if(a.indexOf(tmp[i]) === -1)
				a.push(tmp[i]);
		}

		this.bounds = a;

		this.method = _t('unique values');

		return a;

	};


	this.getClass = function(value) {

		for (var i = 0; i < this.bounds.length; i++) {

			if(this.is_uniqueValues == true) {

				if(value == this.bounds[i]) {
					return i;
				}
			} else {
				if(parseFloat(value) <= this.bounds[i + 1]) {
					return i;
				}
			}
		}

		return _t("Unable to get value's class.");

	};

	this.getRanges = function() {

		return this.ranges;

	};

	this.getRangeNum = function(value) {

		var bounds, i;

		for (var i = 0; i < this.ranges.length; i++) {
			bounds = this.ranges[i].split(/ - /);
			if (value <= parseFloat(bounds[1])) {
				return i;
			}
		}
	}

	this.getInnerRanges = function() {

		if(this.inner_ranges != null)
			return this.inner_ranges;


		var a = new Array();
		var tmp = this.sorted();

		var cnt = 1;

		for (var i = 0; i < tmp.length; i++) {

			if(i == 0) var range_firstvalue = tmp[i];

			if(parseFloat(tmp[i]) > parseFloat(this.bounds[cnt])) {

				a[cnt - 1] = '' + range_firstvalue + this.separator + tmp[i-1];

				var range_firstvalue =  tmp[i];

				cnt++;

			}

			if(cnt == (this.bounds.length - 1)) {
				a[cnt - 1] = '' + range_firstvalue + this.separator + tmp[tmp.length-1];

				this.inner_ranges = a;
				return this.inner_ranges;
			}


		}

	};

	this.getSortedlist = function() {

		return this.sorted().join(', ');

	};

	this.getHtmlLegend = function(colors, legend, counter, callback, mode, order) {

		var cnt= '';
		var elements = new Array();

		var ccolors, lg, getcounter, fn;

		this.doCount();

		if(colors != null) {
			ccolors = colors;
		}
		else {
			ccolors = this.colors;
		}

		if(legend != null) {
			lg = legend;
		}
		else {
			lg =  'Legend';
		}

		if(counter != null) {
			getcounter = true;
		}
		else {
			getcounter = false;
		}

		if(callback != null) {
			fn = callback;
		}
		else {
			fn = function(o) {return o;};
		}
		if(mode == null) {
			mode = 'default';
		}
		if(mode == 'discontinuous') {
			this.getInnerRanges();
			if(this.counter.indexOf(0) !== -1) {
			if(this.silent) this.log("[silent mode] " + _t("Geostats cannot apply 'discontinuous' mode to the getHtmlLegend() method because some classes are not populated.\nPlease switch to 'default' or 'distinct' modes. Exit!"), true);
				else throw new TypeError(_t("Geostats cannot apply 'discontinuous' mode to the getHtmlLegend() method because some classes are not populated.\nPlease switch to 'default' or 'distinct' modes. Exit!"));
				return;
			}

		}
		if(order !== 'DESC') order = 'ASC';

		if(ccolors.length < this.ranges.length) {
			if(this.silent) this.log("[silent mode] " + _t('The number of colors should fit the number of ranges. Exit!'), true);
			else throw new TypeError(_t('The number of colors should fit the number of ranges. Exit!'));
			return;
		}

		if(this.is_uniqueValues == false) {

			for (var i = 0; i < (this.ranges.length); i++) {
				if(getcounter===true) {
					cnt = ' <span class="geostats-legend-counter">(' + this.counter[i] + ')</span>';
				}

				var tmp = this.ranges[i].split(this.separator);

				var start_value = parseFloat(tmp[0]).toFixed(this.precision);
				var end_value = parseFloat(tmp[1]).toFixed(this.precision);


				if(mode == 'distinct' && i != 0) {

					if(isInt(start_value)) {
						start_value = parseInt(start_value) + 1;
						if(this.precisionflag == 'manual' && this.precision != 0) start_value = parseFloat(start_value).toFixed(this.precision);
					} else {

						start_value = parseFloat(start_value) + (1 / Math.pow(10,this.precision));
						start_value = parseFloat(start_value).toFixed(this.precision);
					}
				}

				if(mode == 'discontinuous') {

					var tmp = this.inner_ranges[i].split(this.separator);

					var start_value = parseFloat(tmp[0]).toFixed(this.precision);
					var end_value = parseFloat(tmp[1]).toFixed(this.precision);

				}

				var el = fn(start_value) + this.legendSeparator + fn(end_value);

				var block = '<div><div class="geostats-legend-block" style="background-color:' + ccolors[i] + '"></div> ' + el + cnt + '</div>';
				elements.push(block);
			}

		} else {

			for (var i = 0; i < (this.bounds.length); i++) {
				if(getcounter===true) {
					cnt = ' <span class="geostats-legend-counter">(' + this.counter[i] + ')</span>';
				}
				var el = fn(this.bounds[i]);
				var block = '<div><div class="geostats-legend-block" style="background-color:' + ccolors[i] + '"></div> ' + el + cnt + '</div>';

				elements.push(block);
			}

		}

		if(order === 'DESC') elements.reverse();

		var content  = '<div class="geostats-legend"><div class="geostats-legend-title">' + _t(lg) + '</div>';
		for (var i = 0; i < (elements.length); i++) {
			content += elements[i];
		}
		content += '</div>';

		return content;
	};




	this.objectID = new Date().getUTCMilliseconds();
	this.log('Creating new geostats object');

	if(typeof a !== 'undefined' && a.length > 0) {
		this.serie = a;
		this.setPrecision();
		this.log('Setting serie (' + a.length + ') : ' + a.join());
	} else {
		this.serie = Array();

	};

	this.getJenks = this.getClassJenks;
	this.getJenks2 = this.getClassJenks2;
	this.getGeometricProgression = this.getClassGeometricProgression;
	this.getEqInterval = this.getClassEqInterval;
	this.getQuantile = this.getClassQuantile;
	this.getStdDeviation = this.getClassStdDeviation;
	this.getUniqueValues = this.getClassUniqueValues;
	this.getArithmeticProgression = this.getClassArithmeticProgression;

};


return geostats;
})();

export default geostats;
