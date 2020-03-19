# coding: utf8
from alinea.caribu.CaribuScene import CaribuScene
from alinea.caribu.sky_tools import turtle
import time as t
import pandas as pd
import numpy as np

### Calcul du rayonnement diffus via Caribu ###
def apply_caribu(lscene, energy=1, azimuths=4, zeniths=5, diffuse_model='soc', scene_unit='mm', espacement=50, NBlignes=1, NBcolonnes=1):
    # generation des sources
    from alinea.caribu.sky_tools import GenSky, GetLight
    #: Diffuse light sources : Get the energy and positions of the source for each sector as a string
    sky_string = GetLight.GetLight(GenSky.GenSky()(energy, diffuse_model, azimuths, zeniths))  #: (Energy, soc/uoc, azimuths, zeniths)
    # Convert string to list in order to be compatible with CaribuScene input format
    sky = []
    for string in sky_string.split('\n'):
        if len(string) != 0:
            string_split = string.split(' ')
            t = tuple((float(string_split[0]), tuple((float(string_split[1]), float(string_split[2]), float(string_split[3])))))
            sky.append(t)
    # Generation du pattern
    Pattern=(-espacement/2, -espacement/2, espacement*(NBlignes-1)+espacement/2, espacement*(NBcolonnes-1)+espacement/2)
    c_scene=CaribuScene(scene=lscene, light=sky, pattern=Pattern, scene_unit=scene_unit)
    if Pattern!=None:
        output=c_scene.run(direct=True,infinite=True)
    else:
        output=c_scene.run(direct=True,infinite=False)
    raw, c_res = output
    return c_res['default_band']

#appelée à la fin de chaque jour
def apply_caribu_lgrass(lstring,lscene,TPS,current_day,tiller_appearance,nb_plantes,dico_caribu,day):
    BiomProd = [0.] * (nb_plantes)
    if current_day > day :
        timing_method1 = t.time()
        res = apply_caribu(lscene, energy=dico_caribu['meteo'][dico_caribu['meteo'].experimental_day == current_day].PAR_incident.iloc[0],
                           azimuths=dico_caribu['azimuths'], zeniths=dico_caribu['zeniths'], diffuse_model=dico_caribu['diffuse_model'],
                           scene_unit=dico_caribu['scene_unit'])
        print('temps d exec de caribu:', t.time() - timing_method1)
        for id, v in res['Ei'].items():
            dico_caribu['Ray'][lstring[id][0].id_plante] += (v * (res['area'][id] * 1E-6))  # v: MJ m-2, area: mm2, Ray: MJ PAR
            id_plante = lstring[id][0].id_plante
            id_talle = lstring[id][0].id_talle
            area = res['area'][id]
            dico_caribu['radiation_interception'] = dico_caribu['radiation_interception'].append(pd.DataFrame(
                {'id_plante': [id_plante], 'id_talle': [id_talle], 'date': [current_day],
                 'organ': lstring[id].name, 'Ei': [v], 'area': [area]}))

        # ------------------------------------------------------------------------------------------------
        # --------------------------- Conditions for tiller regression  ----------------------------------
        # ------------------------------------------------------------------------------------------------
        # Principle: if a the youngest tiller of a plant does not intercept enough light radiations, it
        # will die.
        # At the end of each day, radiations intercepted by the youngest tillers of each plant is
        # calculated. The one of this tiller that intercept the less radiation and less radiation than the
        # radiation_threshold will die.
        # ------------------------------------------------------------------------------------------------
        if dico_caribu['option_tiller_regression'] == True and len(tiller_appearance) > 0:
            tiller_to_remove = pd.DataFrame()

            for id_plante in np.unique(tiller_appearance.id_plante):
                plant_tillers = tiller_appearance[tiller_appearance.id_plante == id_plante]
                youngest_tillers = plant_tillers[
                    plant_tillers.appearance_date == max(plant_tillers.appearance_date)]
                youngest_tillers_radiations = pd.DataFrame()

                for id_talle in youngest_tillers.id_talle:
                    select_plant = dico_caribu['radiation_interception'].id_plante == id_plante
                    select_tiller = dico_caribu['radiation_interception'].id_talle == id_talle
                    time_condition = current_day - dico_caribu['period_considered_tiller_regression'] <= dico_caribu['radiation_interception'].date
                    df = dico_caribu['radiation_interception'][select_plant & select_tiller & time_condition]
                    tiller_raditation = (df.Ei * df.area).sum() / df.area.sum()
                    youngest_tillers_radiations = youngest_tillers_radiations.append(
                        pd.DataFrame({'id_talle': [id_talle], 'Ei_tiller': [tiller_raditation]}))

                potential_tiller_to_remove = youngest_tillers_radiations[
                    youngest_tillers_radiations.Ei_tiller == min(youngest_tillers_radiations.Ei_tiller)]
                if potential_tiller_to_remove.Ei_tiller.item() <= dico_caribu['radiation_threshold']:
                    tiller_to_remove = tiller_to_remove.append(pd.DataFrame(
                        {'id_plante': [id_plante], 'id_talle': [potential_tiller_to_remove.id_talle.item()]}))

        if dico_caribu['option_mophogenetic_regulation_by_carbone'] == True:
            for ID in xrange(nb_plantes):
                BiomProd[ID] = dico_caribu['Ray'][ID] * dico_caribu['RUE']  # Ray: MJ PAR ; RUE : g MJ-1
                print('Plante %s, Ray: %s, BiomProd: %s' % (ID, dico_caribu['Ray'][ID], BiomProd[ID]))
        print(BiomProd, dico_caribu['radiation_interception'], dico_caribu['Ray'])
    return BiomProd, dico_caribu['radiation_interception'], dico_caribu['Ray']