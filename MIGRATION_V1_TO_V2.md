# Migration Guide: v1.x → v2.0

## Summary of Changes

v2.0 introduces **multi-device support** with breaking changes to entity IDs.

### What's New
- ✅ Support for multiple scooters (multi-instance)
- ✅ MQTT Discovery (automatic sensor configuration)
- ✅ Improved device identification with IMEI
- ✅ Device selector for services

### Breaking Changes
- ❌ IMEI is now **required**
- ❌ Entity IDs now include IMEI suffix
- ❌ Single-instance restriction removed

## Migration Steps

### Step 1: Backup

Before updating, backup your Home Assistant configuration:

```bash
# Backup your Home Assistant config
cp -r ~/.homeassistant ~/.homeassistant.backup

# Or if using Docker/HAOS, backup via UI:
# Settings → System → Backups → Create Backup
```

### Step 2: Document Current Setup

Take note of:
- **Current entity IDs** (e.g., `sensor.silence_scooter_speed`)
- **Automations** using these entities
- **Dashboards** with scooter cards
- **Scripts/scenes** referencing scooter entities

**Quick way to find all Silence entities:**
1. Go to **Developer Tools → States**
2. Filter for "silence_scooter"
3. Take screenshots or export the list

### Step 3: Update Integration

1. **Via HACS**:
   - Open HACS → Integrations
   - Find "Silence Scooter"
   - Click "Update"
   - Restart Home Assistant

2. **Manual Update**:
   - Download latest release from [Releases page](https://github.com/noiwid/silence-scooter-homeassistant/releases)
   - Replace `custom_components/silencescooter` folder
   - Restart Home Assistant

### Step 4: Enter IMEI

After restart:

1. Go to **Settings → Devices & Services**
2. Find **Silence Scooter** integration
3. You'll see a notification: **"Migration Required"**
4. Click **"Configure"**
5. Enter your **15-digit IMEI**
6. Click **Submit**

**Finding your IMEI:**
- Check your scooter frame (near VIN plate)
- Look in Silence mobile app: Settings → Device Info
- Check Silence Private Server logs
- Original purchase documentation

### Step 5: Update Automations

Replace old entity IDs with new ones. The new entity IDs include the **last 4 digits** of your IMEI as a suffix.

**Example with IMEI ending in 9012:**

#### Before (v1.x):
```yaml
automation:
  - alias: "Notify when scooter starts moving"
    trigger:
      - platform: state
        entity_id: sensor.silence_scooter_speed
        from: "0"
    action:
      - service: notify.mobile_app
        data:
          message: "Scooter is moving!"
```

#### After (v2.0):
```yaml
automation:
  - alias: "Notify when scooter starts moving"
    trigger:
      - platform: state
        entity_id: sensor.silence_scooter_speed_9012
        from: "0"
    action:
      - service: notify.mobile_app
        data:
          message: "Scooter is moving!"
```

**Common Entity ID Migrations:**

| v1.x Entity ID | v2.0 Entity ID (example: IMEI ending in 9012) |
|----------------|----------------------------------------------|
| `sensor.silence_scooter_speed` | `sensor.silence_scooter_speed_9012` |
| `sensor.silence_scooter_battery_soc` | `sensor.silence_scooter_battery_soc_9012` |
| `sensor.silence_scooter_odo` | `sensor.silence_scooter_odo_9012` |
| `sensor.scooter_last_trip_distance` | `sensor.scooter_last_trip_distance_9012` |
| `number.scooter_odo_debut` | `number.scooter_odo_debut_9012` |
| `switch.stop_trip_now` | `switch.stop_trip_now_9012` |
| `device_tracker.silence_scooter` | `device_tracker.silence_scooter_9012` |

**Tip:** Use Home Assistant's built-in search/replace in automations:
1. Settings → Automations & Scenes
2. Edit each automation
3. Use YAML mode and find/replace entity IDs

### Step 6: Update Dashboards

Update any Lovelace cards referencing old entity IDs:

1. Go to your dashboard
2. Click **Edit Dashboard**
3. Edit each card using Silence entities
4. Update entity IDs to include IMEI suffix
5. Save changes

**Example Card Update:**

#### Before:
```yaml
type: entities
entities:
  - entity: sensor.silence_scooter_speed
  - entity: sensor.silence_scooter_battery_soc
  - entity: sensor.scooter_last_trip_distance
```

#### After:
```yaml
type: entities
entities:
  - entity: sensor.silence_scooter_speed_9012
  - entity: sensor.silence_scooter_battery_soc_9012
  - entity: sensor.scooter_last_trip_distance_9012
```

### Step 7: Update MQTT Configuration (if using manual config)

If you were using manual MQTT configuration in `configuration.yaml`:

1. **Remove old MQTT sensors** (without IMEI in topics)
2. **Add new MQTT sensors** with IMEI-based topics
3. See `examples/silence.yaml` for the new format

**Or better yet**: Use **MQTT Discovery** (automatic) - see below.

### Step 8: Enable MQTT Discovery (Recommended)

v2.0 includes **automatic MQTT Discovery**. This means you don't need manual MQTT configuration anymore!

1. **Remove manual MQTT config** from `configuration.yaml`
2. Restart Home Assistant
3. Integration will automatically publish MQTT Discovery configs
4. All sensors/buttons will appear automatically

**Verify MQTT Discovery is working:**
1. Go to **Settings → Devices & Services → MQTT**
2. Look for "Silence Scooter (9012)" device
3. Check that sensors are listed under it

### Step 9: Test

Verify everything works:

- [ ] Sensors updating correctly
- [ ] Trip detection working
- [ ] Device tracker showing location
- [ ] Services working (reset_tracked_counters)
- [ ] Automations triggering correctly
- [ ] Dashboard displaying data
- [ ] No errors in logs

**Check logs:**
```
Settings → System → Logs
Filter: "silencescooter"
```

### Step 10: Clean Up

Once everything works:

1. **Delete backup** (if confident migration succeeded)
2. **Remove old MQTT configs** (if using MQTT Discovery)
3. **Update documentation** (notes, comments in configs)

## Multiple Scooters Setup

If you have **multiple scooters**, you can now add them:

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "Silence Scooter"
3. Enter **second scooter's IMEI**
4. Configure settings
5. Repeat for each scooter

Each scooter will have:
- Separate device in Home Assistant
- Unique entity IDs (with different IMEI suffixes)
- Isolated trip tracking and statistics

## Rollback (if needed)

If you encounter issues and need to rollback:

### Option 1: Restore from Backup
```bash
# Restore backup
cp -r ~/.homeassistant.backup ~/.homeassistant
# Or use Home Assistant UI: Settings → System → Backups → Restore
```

### Option 2: Downgrade Integration

1. **Via HACS**:
   - HACS → Integrations → Silence Scooter
   - Click "Redownload"
   - Select version "1.0.0"
   - Restart Home Assistant

2. **Manual Downgrade**:
   - Download v1.0.0 from [Releases](https://github.com/noiwid/silence-scooter-homeassistant/releases/tag/v1.0.0)
   - Replace `custom_components/silencescooter` folder
   - Restart Home Assistant

### Option 3: Fresh Install

If migration is completely broken:

1. **Remove integration**: Settings → Devices & Services → Silence Scooter → Delete
2. **Clear entity registry**: Developer Tools → States → Delete old entities
3. **Reinstall integration**: Add Integration → Silence Scooter
4. **Enter IMEI** and reconfigure

## Troubleshooting

### Problem: Migration prompt doesn't appear

**Solution:**
1. Force reconfiguration: Settings → Devices & Services → Silence Scooter → "..."  → Reconfigure
2. Or delete and reinstall integration

### Problem: Entity IDs haven't changed

**Solution:**
- Entity IDs are cached. Restart Home Assistant twice
- Or manually delete old entities: Developer Tools → States → Delete

### Problem: Sensors not updating after migration

**Solution:**
1. Check MQTT broker connection
2. Verify IMEI matches Silence Private Server config
3. Check logs for errors: `silencescooter` filter

### Problem: "Invalid IMEI" error

**Solution:**
- IMEI must be **14-15 digits**
- Remove spaces, dashes, or other characters
- Verify correct IMEI from scooter documentation

### Problem: Automations broken after migration

**Solution:**
1. Check automation YAML for old entity IDs
2. Use find/replace: `silence_scooter_` → `silence_scooter_9012_` (replace 9012 with your IMEI suffix)
3. Test each automation individually

### Problem: Dashboard shows "Entity not available"

**Solution:**
- Update entity IDs in all dashboard cards
- Verify entities exist: Developer Tools → States
- Clear browser cache

### Problem: Trip history lost

**Solution:**
- Trip history is stored in `history.json` with old entity IDs
- History will rebuild with new trips
- **Old history is preserved** but won't display in UI (different entity IDs)
- To migrate history: manually edit `history.json` and update entity IDs (advanced)

## Getting Help

If you encounter issues during migration:

1. **Check logs**: Settings → System → Logs (filter: "silencescooter")
2. **GitHub Issues**: [Report a bug](https://github.com/noiwid/silence-scooter-homeassistant/issues)
3. **Include in your report**:
   - Home Assistant version
   - Integration version (before and after)
   - IMEI last 4 digits only (for privacy)
   - Relevant log errors
   - Steps already attempted

## FAQ

### Q: Will I lose my trip history?

**A:** No, trip history is preserved in `history.json`. However, it won't display in the UI due to entity ID changes. New trips will use the new entity IDs.

### Q: Can I use v1.x and v2.0 simultaneously?

**A:** No, you must choose one version. v2.0 replaces v1.x completely.

### Q: Do I need to reconfigure Silence Private Server?

**A:** Only if adding multiple scooters. For single scooter, no changes needed on server side.

### Q: What if I don't know my IMEI?

**A:** Check:
1. Silence mobile app: Settings → Device Info
2. Scooter frame near VIN plate
3. Silence Private Server logs (look for 15-digit numbers)
4. Original purchase documentation

### Q: Can I change the IMEI after migration?

**A:** Yes, go to Settings → Devices & Services → Silence Scooter → Configure. However, this will change entity IDs again.

### Q: Will MQTT Discovery work with my existing MQTT broker?

**A:** Yes, as long as:
- MQTT broker is running and connected
- MQTT integration is configured in Home Assistant
- Discovery is enabled (default)

---

**Migration completed successfully?** Consider:
- ⭐ Star the [GitHub repository](https://github.com/noiwid/silence-scooter-homeassistant)
- 📝 Share feedback in [Discussions](https://github.com/noiwid/silence-scooter-homeassistant/discussions)
- 🐛 Report any issues on [GitHub](https://github.com/noiwid/silence-scooter-homeassistant/issues)

**Thank you for using Silence Scooter Home Assistant integration!**
