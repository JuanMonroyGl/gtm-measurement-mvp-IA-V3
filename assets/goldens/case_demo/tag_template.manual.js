<script>
  var element = {{Click Element}};
  var getClean = {{JS - Function - Format LowerCase}};
  var getClickText = {{JS - Click Text - Btn and A}};
  var getTextClose = {{JS - Function - Get Text Close}};

  var eventData = { activo: "bancolombia", seccion: "pagina principal" }

  function setDataEvent(data, e, cText, clean, getText) {
    var value = cText;
    if (typeof value === 'function') { value = value(e); }
    if (!value) {
      value = (typeof getText === 'function') ? getText(e) : getText;
    }
    value = (typeof clean === 'function') ? clean(value || '') : (value || '');
    if(e.closest('.header-main_cont .header-main_nav .header-menu_link')) {
        data['elemento'] = value;
        data['flujo'] = "principal";
        data['ubicacion'] = "barra arriba";

        if (document.location.href.search('appspot.com') == -1) {analytics.track('Clic Menu', data)};
        return;
    }
    else if(e.closest('.wcmbc-menu-swiper-container .swiper-wrapper .swiper-slide')) {
        data['elemento'] = value;
        data['flujo'] = "mitad";
        data['ubicacion'] = "tab del medio";

        if (document.location.href.search('appspot.com') == -1) {analytics.track('Clic Tab', data)};
        return;
    }// Mapping manual por card ID porque el DOM no expone un selector de título suficientemente confiable.
    else if (
      e.closest(
        '#recomendado_1 .card-footer-cwss2 .btn-outline-brand, ' +
        '#recomendado_2 .card-footer-cwss2 .btn-outline-brand, ' +
        '#recomendado_3 .card-footer-cwss2 .btn-outline-brand'
      )
      ) {
      var card = e.closest('#recomendado_1, #recomendado_2, #recomendado_3');

      var cardsData = {
        recomendado_1: {
          elemento: 'conoce los beneficios',
          tituloCard: 'tu tarjeta de credito te ofrece mas'
        },
        recomendado_2: {
          elemento: 'descubre como',
          tituloCard: 'te cortaron la luz'
        },
        recomendado_3: {
          elemento: 'descubre mas',
          tituloCard: 'sacale provecho a los beneficios de tu tarjeta'
        }
      };

      var cardInfo = cardsData[card.id];

      data['elemento'] = cardInfo.elemento;
      data['flujo'] = 'mas abajo';
      data['ubicacion'] = 'tab del medio';
      data['tituloCard'] = cardInfo.tituloCard;

      if (document.location.href.search('appspot.com') == -1) {
        analytics.track('Clic Card', data);
      }

      return;
    }
    else if(e.closest('.lista-preguntas ul a')) {
        data['elemento'] = value;
        data['flujo'] = "mitad de abajo";
        data['ubicacion'] = "lo mas consultado";

        if (document.location.href.search('appspot.com') == -1) {analytics.track('Clic Tab', data)};
        return;
    }
  }

  setDataEvent(eventData, element, getClickText, getClean, getTextClose);
</script>