function isScrolledIntoView(elem)
{
    var docViewTop = $(window).scrollTop();
    var docViewBottom = docViewTop + $(window).height();

    var elemTop = $(elem).offset().top;
    var elemBottom = elemTop + $(elem).height();

    return ((elemBottom <= docViewBottom) && (elemTop >= docViewTop));
}
var simplePopup = (function() {
    var simplePopup = function(pattern) {
        this.pattern = pattern;
        this.target = false;
        var $container = $(document.body);
        this.tooltip = $('<div />').addClass('popup');
        $container.append(this.tooltip);
        this.tooltip.css({
            'background': '#ffa',
            'border' : '3px solid #A0A090',
            'padding': '3px 8px 3px 8px',
            'display': 'none',
            'width': '100%',
            'position': 'fixed',
            'z-index': '100',
        });
        var thispopup = this
    MathJax.Hub.Queue(function () {
        $container.on('mouseover', thispopup.pattern, {thispopup:thispopup}, thispopup.mouseover);
        $container.on('mouseout', thispopup.pattern,  {thispopup:thispopup}, thispopup.mouseout);
    });
this.showTooltip = false;
    };
    simplePopup.showTooltipNow = function(thispopup) {
        thispopup.showTooltip = true;
        thispopup.tooltip.stop(true, true);
        //$tooltip.append($root.clone());
        thispopup.tooltip.css({
            top: 0,
        });
        thispopup.tooltip.fadeIn();

    };
    simplePopup.prototype.keepvisible = function(e)
    {
        var thispopup = e.data.thispopup;

        thispopup.tooltip.stop();
        thispopup.tooltip.css({
            'opacity':'initial'  //problem here if opacity is set in render method
        });
    };
    simplePopup.prototype.mouseover = function(e) {
        var thispopup = e.data.thispopup;
        var a = e.currentTarget;
        var $number = $(a.hash);
        var $root = $number.closest('div');
        if(thispopup.target) {
            thispopup.target.css({
                'background':'#fff',
            })
            thispopup.target = false;
        }

        if(isScrolledIntoView($root)) {
            thispopup.target = $root;
            $root.css({
                'background':'#ffa',
            })
        } else {
            thispopup.showTooltip = true;
            var $container = $(document.body);
            var bounds = $(a).offset();
            var containerBounds = $container.offset();
            thispopup.tooltip.bind('mouseover', {thispopup:thispopup}, thispopup.keepvisible);
            thispopup.tooltip.bind('mouseout',  {thispopup:thispopup}, thispopup.mouseout);
            thispopup.tooltip.stop(true, true);
            //thispopup.tooltip.append($root.clone());
            thispopup.tooltip.html($root.html());
            thispopup.tooltip.css({
                top: 0,
            });
            thispopup.tooltip.fadeIn();
        }
    }
    simplePopup.prototype.mouseout = function(e) {
        var thispopup = e.data.thispopup;
        thispopup.tooltip.stop(true, true);
        thispopup.tooltip.fadeOut(function () {
            thispopup.tooltip.empty();
        });
        var a = e.currentTarget;
        var $number = $(a.hash);
        var $root = $number.closest('div');
        if(thispopup.target) {
            thispopup.target.css({
                'background':'#fff',
            })
            thispopup.target = false;
        }
    }
    return simplePopup;
})();
$( document ).ready(function() {
var sp = new simplePopup('a[href*="mjx-eqn-"]');
var spimg = new simplePopup('a[href*="img-"]');
var spimg = new simplePopup('a[href*="tbl-"]');
var footnote = new simplePopup('a[href*="footnote-"]');
});
