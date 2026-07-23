/*
================================================================================
 diag_voice_mora.sql
 Diagnostico para p_Voice_Mora_genera
 Rastrea un PIDM o MATRICULA especifico a traves de cada filtro del
 procedimiento para identificar en que paso queda excluido de INTEGRA_COBRANZA.

 USO (PyCharm Database Console):
   Edita el valor de vl_matricula abajo con la matricula a investigar,
   luego ejecuta todo el bloque en la consola (Cmd+Enter / boton Run).
================================================================================
*/

DECLARE
    vl_matricula   VARCHAR2(30) := '240602366';  -- <<<< CAMBIA ESTE VALOR
    vl_pidm        NUMBER;
    vl_campus      tztprog.campus%TYPE;
    vl_nivel       tztprog.nivel%TYPE;
    vl_estatus     tztprog.estatus%TYPE;
    vl_sp          tztprog.sp%TYPE;
    vl_count       NUMBER;
    vl_venc_mes    NUMBER;
    vl_venc_gral   NUMBER;
    vl_saldo_comp  NUMBER;
    vl_saldo_dia   NUMBER;
    vl_threshold   NUMBER;
    vl_msg         VARCHAR2(4000);

    CURSOR c_prog IS
        SELECT a.pidm, a.matricula, a.campus, a.nivel, a.estatus, a.sp,
               a.SGBSTDN_STYP_CODE tipo_alumno
        FROM tztprog a
        WHERE a.matricula = vl_matricula;

BEGIN
    DBMS_OUTPUT.PUT_LINE('================================================================');
    DBMS_OUTPUT.PUT_LINE(' DIAGNOSTICO p_Voice_Mora_genera - MATRICULA: ' || vl_matricula);
    DBMS_OUTPUT.PUT_LINE('================================================================');

    ------------------------------------------------------------------
    -- PASO 0: Existe en tztprog?
    ------------------------------------------------------------------
    FOR r IN c_prog LOOP

        vl_pidm    := r.pidm;
        vl_campus  := r.campus;
        vl_nivel   := r.nivel;
        vl_estatus := r.estatus;
        vl_sp      := r.sp;

        DBMS_OUTPUT.PUT_LINE(CHR(10) || '--- Registro tztprog encontrado ---');
        DBMS_OUTPUT.PUT_LINE('PIDM       : ' || vl_pidm);
        DBMS_OUTPUT.PUT_LINE('CAMPUS     : ' || vl_campus);
        DBMS_OUTPUT.PUT_LINE('NIVEL      : ' || vl_nivel);
        DBMS_OUTPUT.PUT_LINE('ESTATUS    : ' || vl_estatus);
        DBMS_OUTPUT.PUT_LINE('SP         : ' || vl_sp);
        DBMS_OUTPUT.PUT_LINE('TIPO_ALUMNO: ' || r.tipo_alumno);

        ------------------------------------------------------------------
        -- PASO 1: join con spriden (spriden_change_ind is null)
        ------------------------------------------------------------------
        SELECT COUNT(1) INTO vl_count
        FROM spriden b
        WHERE b.spriden_pidm = vl_pidm
          AND b.spriden_change_ind IS NULL;

        IF vl_count = 0 THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO en JOIN spriden (no existe registro con spriden_change_ind IS NULL para este pidm).');
        ELSE
            DBMS_OUTPUT.PUT_LINE('OK  - JOIN spriden pasa (' || vl_count || ' registro(s)).');
        END IF;

        ------------------------------------------------------------------
        -- PASO 2: join con SZVCAMP
        ------------------------------------------------------------------
        SELECT COUNT(1) INTO vl_count
        FROM SZVCAMP
        WHERE SZVCAMP_CAMP_CODE = vl_campus;

        IF vl_count = 0 THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO en JOIN SZVCAMP (campus "' || vl_campus || '" no existe en SZVCAMP).');
        ELSE
            DBMS_OUTPUT.PUT_LINE('OK  - JOIN SZVCAMP pasa.');
        END IF;

        ------------------------------------------------------------------
        -- PASO 3: join con stvlevl
        ------------------------------------------------------------------
        SELECT COUNT(1) INTO vl_count
        FROM stvlevl
        WHERE STVLEVL_CODE = vl_nivel;

        IF vl_count = 0 THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO en JOIN stvlevl (nivel "' || vl_nivel || '" no existe en stvlevl).');
        ELSE
            DBMS_OUTPUT.PUT_LINE('OK  - JOIN stvlevl pasa.');
        END IF;

        ------------------------------------------------------------------
        -- PASO 4: estatus in ('MA')
        ------------------------------------------------------------------
        IF vl_estatus NOT IN ('MA') THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO por filtro ESTATUS (actual = "' || vl_estatus || '", requerido = MA).');
        ELSE
            DBMS_OUTPUT.PUT_LINE('OK  - Filtro ESTATUS pasa (MA).');
        END IF;

        ------------------------------------------------------------------
        -- PASO 5: goradid exclusion (NOMR, IZZI)
        ------------------------------------------------------------------
        SELECT COUNT(1) INTO vl_count
        FROM goradid
        WHERE goradid_pidm = vl_pidm
          AND GORADID_ADID_CODE IN ('NOMR', 'IZZI');

        IF vl_count > 0 THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO por GORADID (tiene adid NOMR/IZZI). Registros encontrados: ' || vl_count);
        ELSE
            DBMS_OUTPUT.PUT_LINE('OK  - No tiene adid NOMR/IZZI en goradid.');
        END IF;

        ------------------------------------------------------------------
        -- PASO 6: campus habilitado (ZSTPARA HS_COBRANZA_CAM)
        ------------------------------------------------------------------
        SELECT COUNT(1) INTO vl_count
        FROM ZSTPARA
        WHERE ZSTPARA_MAPA_ID = 'HS_COBRANZA_CAM'
          AND ZSTPARA_PARAM_VALOR = vl_campus;

        IF vl_count = 0 THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO: CAMPUS "' || vl_campus || '" no esta en ZSTPARA(HS_COBRANZA_CAM).');
        ELSE
            DBMS_OUTPUT.PUT_LINE('OK  - CAMPUS habilitado en ZSTPARA(HS_COBRANZA_CAM).');
        END IF;

        ------------------------------------------------------------------
        -- PASO 7: nivel habilitado (ZSTPARA HS_COBRANZA_NIV)
        ------------------------------------------------------------------
        SELECT COUNT(1) INTO vl_count
        FROM ZSTPARA
        WHERE ZSTPARA_MAPA_ID = 'HS_COBRANZA_NIV'
          AND ZSTPARA_PARAM_VALOR = vl_nivel;

        IF vl_count = 0 THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO: NIVEL "' || vl_nivel || '" no esta en ZSTPARA(HS_COBRANZA_NIV).');
        ELSE
            DBMS_OUTPUT.PUT_LINE('OK  - NIVEL habilitado en ZSTPARA(HS_COBRANZA_NIV).');
        END IF;

        ------------------------------------------------------------------
        -- PASO 8: calcular Vencimiento_General, Vencimiento_Mes, Saldo_Complemento
        ------------------------------------------------------------------
        SELECT NVL(SUM(NVL(tbraccd_balance, 0)), 0)
        INTO vl_venc_mes
        FROM tbraccd
        WHERE tbraccd_pidm = vl_pidm
          AND TBRACCD_STSP_KEY_SEQUENCE = vl_sp
          AND TRUNC(TBRACCD_EFFECTIVE_DATE) BETWEEN TRUNC(SYSDATE, 'MM') AND LAST_DAY(TRUNC(SYSDATE))
          AND tbraccd_detail_code NOT IN (SELECT codigo FROM TZTINC WHERE campus = vl_campus AND nivel = vl_nivel);

        SELECT NVL(SUM(NVL(tbraccd_balance, 0)), 0)
        INTO vl_venc_gral
        FROM tbraccd
        WHERE tbraccd_pidm = vl_pidm
          AND TBRACCD_STSP_KEY_SEQUENCE = vl_sp
          AND TRUNC(TBRACCD_EFFECTIVE_DATE) < TRUNC(SYSDATE, 'MM');

        SELECT NVL(SUM(NVL(tbraccd_balance, 0)), 0)
        INTO vl_saldo_comp
        FROM tbraccd
        WHERE tbraccd_pidm = vl_pidm
          AND TBRACCD_STSP_KEY_SEQUENCE = vl_sp
          AND TRUNC(TBRACCD_EFFECTIVE_DATE) BETWEEN TRUNC(SYSDATE, 'MM') AND LAST_DAY(TRUNC(SYSDATE))
          AND tbraccd_detail_code IN (SELECT codigo FROM TZTINC WHERE campus = vl_campus AND nivel = vl_nivel);

        DBMS_OUTPUT.PUT_LINE('    Vencimiento_Mes    = ' || vl_venc_mes);
        DBMS_OUTPUT.PUT_LINE('    Vencimiento_General = ' || vl_venc_gral);
        DBMS_OUTPUT.PUT_LINE('    Saldo_Complemento   = ' || vl_saldo_comp);

        IF vl_venc_gral > 0 THEN
            DBMS_OUTPUT.PUT_LINE('    -> Cae en RAMA A del UNION (Vencimiento_General > 0).');
        ELSE
            DBMS_OUTPUT.PUT_LINE('    -> Cae en RAMA B del UNION (Vencimiento_General = 0).');
        END IF;

        ------------------------------------------------------------------
        -- PASO 9: Saldo_Dia vs umbral ZSTPARA(VB_COB_EXCHANGE)
        ------------------------------------------------------------------
        BEGIN
            vl_saldo_dia := PKG_SIU_CHATBOT.f_dashboard_saldodia_Voice(vl_pidm);
        EXCEPTION
            WHEN OTHERS THEN
                vl_saldo_dia := NULL;
                DBMS_OUTPUT.PUT_LINE('    ERROR al calcular Saldo_Dia: ' || SQLERRM);
        END;

        BEGIN
            SELECT TO_NUMBER(ZSTPARA_PARAM_VALOR)
            INTO vl_threshold
            FROM ZSTPARA
            WHERE ZSTPARA_MAPA_ID = 'VB_COB_EXCHANGE'
              AND ZSTPARA_PARAM_ID = vl_campus || vl_nivel;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                vl_threshold := NULL;
            WHEN OTHERS THEN
                vl_threshold := NULL;
        END;

        DBMS_OUTPUT.PUT_LINE('    Saldo_Dia calculado = ' || vl_saldo_dia);
        DBMS_OUTPUT.PUT_LINE('    Umbral ZSTPARA(VB_COB_EXCHANGE) para "' || vl_campus || vl_nivel || '" = ' || vl_threshold);

        IF vl_threshold IS NULL THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO: No existe umbral ZSTPARA(VB_COB_EXCHANGE) para PARAM_ID = "' || vl_campus || vl_nivel || '" (la subconsulta no devuelve fila => comparacion falla).');
        ELSIF vl_saldo_dia IS NULL THEN
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO / INDETERMINADO: Saldo_Dia no se pudo calcular (ver error arriba).');
        ELSIF vl_saldo_dia >= vl_threshold THEN
            DBMS_OUTPUT.PUT_LINE('OK  - Saldo_Dia (' || vl_saldo_dia || ') >= umbral (' || vl_threshold || '). Pasa el filtro de saldo.');
        ELSE
            DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO: Saldo_Dia (' || vl_saldo_dia || ') < umbral (' || vl_threshold || ').');
        END IF;

        ------------------------------------------------------------------
        -- PASO 10: Estado actual en INTEGRA_COBRANZA (antes del truncate,
        -- solo informativo si corres esto ANTES de correr el procedimiento)
        ------------------------------------------------------------------
        BEGIN
            SELECT COUNT(1) INTO vl_count
            FROM migra.INTEGRA_COBRANZA
            WHERE matricula = vl_matricula
              AND sp = vl_sp;

            IF vl_count > 0 THEN
                DBMS_OUTPUT.PUT_LINE(CHR(10) || 'NOTA: Ya existe un registro en INTEGRA_COBRANZA para esta matricula/sp (de una corrida previa).');
            ELSE
                DBMS_OUTPUT.PUT_LINE(CHR(10) || 'NOTA: No hay registro actual en INTEGRA_COBRANZA para esta matricula/sp.');
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                DBMS_OUTPUT.PUT_LINE('No se pudo consultar INTEGRA_COBRANZA: ' || SQLERRM);
        END;

        DBMS_OUTPUT.PUT_LINE('----------------------------------------------------------------');

    END LOOP;

    IF SQL%ROWCOUNT = 0 THEN
        NULL; -- cursor for loop doesn't set SQL%ROWCOUNT reliably, handled below
    END IF;

    -- Verifica si el cursor no encontro nada
    SELECT COUNT(1) INTO vl_count FROM tztprog WHERE matricula = vl_matricula;
    IF vl_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('>>> EXCLUIDO desde el origen: la matricula "' || vl_matricula || '" no existe en TZTPROG.');
    END IF;

    DBMS_OUTPUT.PUT_LINE('================================================================');
    DBMS_OUTPUT.PUT_LINE(' FIN DIAGNOSTICO');
    DBMS_OUTPUT.PUT_LINE('================================================================');

END;
/
